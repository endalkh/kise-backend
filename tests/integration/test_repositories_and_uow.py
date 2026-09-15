"""Repositories and the Unit of Work, against a real SQLite database.

Three things are being proved here, and none of them can be proved with fakes:

1. **Ownership isolation** — a query for someone else's id returns nothing (FR-1.4).
2. **Write-back** — mutating a loaded aggregate reaches the database on commit, even though
   SQLAlchemy cannot see a change made to an object it does not own.
3. **Event timing** — events are published after a successful commit, and not at all after a
   rollback.
"""

from __future__ import annotations

from datetime import UTC, date, datetime

import pytest

from kise.expense_tracking.application.commands import ExpenseFilter
from kise.expense_tracking.domain.errors import (
    CategoryNotFound,
    ExpenseNotFound,
    FixedExpenseNotFound,
)
from kise.expense_tracking.domain.events import ExpenseRecorded
from kise.expense_tracking.domain.models import (
    Category,
    Expense,
    FixedExpense,
    default_categories_for,
)
from kise.identity.domain.errors import OwnerNotFound
from kise.identity.domain.events import OwnerRegistered
from kise.identity.domain.models import EmailAddress, Owner, PasswordHash
from kise.platform.database import build_engine, build_session_factory, create_all
from kise.platform.event_bus import InProcessEventBus
from kise.platform.unit_of_work import KiseUnitOfWork, build_unit_of_work_factory
from kise.shared_kernel.domain.calendar import CalendarKind, Period, SpendDate
from kise.shared_kernel.domain.identifiers import CategoryId, ExpenseId, FixedExpenseId, OwnerId
from kise.shared_kernel.domain.money import Money

NOW = datetime(2026, 9, 4, 20, 0, tzinfo=UTC)
HAMLE_2018 = Period(CalendarKind.ETHIOPIAN, 2018, 11)
NEHASE_2018 = Period(CalendarKind.ETHIOPIAN, 2018, 12)


@pytest.fixture
def session_factory():
    engine = build_engine("sqlite://")
    create_all(engine)
    yield build_session_factory(engine)
    engine.dispose()


@pytest.fixture
def event_bus() -> InProcessEventBus:
    return InProcessEventBus()


@pytest.fixture
def uow_factory(session_factory, event_bus):
    return build_unit_of_work_factory(session_factory, event_bus)


@pytest.fixture
def uow(uow_factory) -> KiseUnitOfWork:
    return uow_factory()


def an_owner(email: str = "selam@example.com") -> Owner:
    return Owner.register(
        email=EmailAddress(email),
        password_hash=PasswordHash("$2b$12$hash"),
        display_name="Selam Tesfaye",
        registered_at=NOW,
    )


def a_category(owner: Owner, name: str = "Rent") -> Category:
    return Category.create(owner_id=owner.id, name=name, name_am="ቤት ኪራይ")


# -- Owner repository ---------------------------------------------------


def test_owner_is_added_found_and_rehydrated(uow_factory):
    owner = an_owner()
    writer = uow_factory()
    writer.owners.add(owner)
    writer.commit()

    # A different Unit of Work, so the result comes from the database and not the identity map.
    reader = uow_factory()
    found = reader.owners.find_by_email(EmailAddress("SELAM@example.com"))
    assert found is not None
    assert found.id == owner.id
    assert found.display_name == "Selam Tesfaye"
    assert found is not owner
    assert reader.owners.email_exists(EmailAddress("selam@example.com"))
    assert not reader.owners.email_exists(EmailAddress("nobody@example.com"))


def test_missing_owner_raises(uow):
    with pytest.raises(OwnerNotFound):
        uow.owners.get(OwnerId.new())


def test_the_identity_map_returns_the_same_instance(uow):
    owner = an_owner()
    uow.owners.add(owner)
    uow.commit()
    assert uow.owners.get(owner.id) is owner


# -- write-back ---------------------------------------------------------


def test_mutating_a_loaded_aggregate_is_written_back_on_commit(uow_factory):
    first = uow_factory()
    owner = an_owner()
    first.owners.add(owner)
    first.commit()
    owner_id = owner.id

    second = uow_factory()
    loaded = second.owners.get(owner_id)
    loaded.rename("Selam T.")
    loaded.prefer_calendar("gregorian")
    second.commit()  # no explicit "save" call anywhere

    third = uow_factory()
    reloaded = third.owners.get(owner_id)
    assert reloaded.display_name == "Selam T."
    assert reloaded.preferences.calendar is CalendarKind.GREGORIAN


def test_rollback_leaves_nothing_behind(uow_factory):
    doomed = uow_factory()
    owner = an_owner()
    doomed.owners.add(owner)
    doomed.rollback()

    fresh = uow_factory()
    with pytest.raises(OwnerNotFound):
        fresh.owners.get(owner.id)


# -- ownership isolation ------------------------------------------------


def test_one_owner_cannot_read_anothers_records(uow_factory):
    setup = uow_factory()
    mine, theirs = an_owner("mine@example.com"), an_owner("theirs@example.com")
    setup.owners.add(mine)
    setup.owners.add(theirs)
    my_category = a_category(mine)
    their_category = a_category(theirs)
    setup.categories.add(my_category)
    setup.categories.add(their_category)
    my_expense = Expense.record(
        owner_id=mine.id,
        category_id=my_category.id,
        amount=Money.from_major("100"),
        spent_on=SpendDate.from_ethiopian(2018, 11, 15),
    )
    setup.expenses.add(my_expense)
    commitment = FixedExpense.schedule(
        owner_id=mine.id,
        category_id=my_category.id,
        title="House rent",
        amount=Money.from_major("8000"),
        start_period=HAMLE_2018,
        due_day=5,
    )
    setup.fixed_expenses.add(commitment)
    setup.commit()

    reader = uow_factory()
    # Reading my own records works.
    assert reader.categories.get(mine.id, my_category.id).id == my_category.id
    # Reading theirs with my id does not.
    with pytest.raises(CategoryNotFound):
        reader.categories.get(mine.id, their_category.id)
    with pytest.raises(ExpenseNotFound):
        reader.expenses.get(theirs.id, my_expense.id)
    with pytest.raises(FixedExpenseNotFound):
        reader.fixed_expenses.get(theirs.id, commitment.id)
    assert reader.categories.list_for_owner(theirs.id) == [
        reader.categories.get(theirs.id, their_category.id)
    ]
    assert reader.expenses.list(ExpenseFilter(owner_id=theirs.id)) == []
    assert reader.fixed_expenses.list_for_owner(theirs.id) == []


# -- Category repository ------------------------------------------------


def test_seeding_defaults_then_listing_them(uow_factory):
    setup = uow_factory()
    owner = an_owner()
    setup.owners.add(owner)
    setup.categories.add_all(default_categories_for(owner.id))
    setup.commit()

    reader = uow_factory()
    live = reader.categories.list_for_owner(owner.id)
    assert len(live) == 10
    assert [c.name for c in live] == sorted(c.name for c in live)  # ordered by name


def test_archived_categories_are_hidden_unless_asked_for(uow_factory):
    setup = uow_factory()
    owner = an_owner()
    setup.owners.add(owner)
    category = a_category(owner)
    setup.categories.add(category)
    setup.commit()

    archiver = uow_factory()
    archiver.categories.get(owner.id, category.id).archive()
    archiver.commit()

    reader = uow_factory()
    assert reader.categories.list_for_owner(owner.id) == []
    assert len(reader.categories.list_for_owner(owner.id, include_archived=True)) == 1


def test_removing_a_category(uow_factory):
    setup = uow_factory()
    owner = an_owner()
    setup.owners.add(owner)
    category = a_category(owner)
    setup.categories.add(category)
    setup.commit()

    remover = uow_factory()
    remover.categories.remove(remover.categories.get(owner.id, category.id))
    remover.commit()

    reader = uow_factory()
    with pytest.raises(CategoryNotFound):
        reader.categories.get(owner.id, category.id)


# -- Expense repository -------------------------------------------------


@pytest.fixture
def owner_with_expenses(uow_factory):
    setup = uow_factory()
    owner = an_owner()
    setup.owners.add(owner)
    food = Category.create(owner_id=owner.id, name="Food")
    transport = Category.create(owner_id=owner.id, name="Transport")
    setup.categories.add(food)
    setup.categories.add(transport)
    for day, amount, category in (
        (date(2026, 7, 8), "50", food),  # ሐምሌ 1
        (date(2026, 7, 22), "120", transport),  # ሐምሌ 15
        (date(2026, 8, 6), "75", food),  # ሐምሌ 30
        (date(2026, 8, 7), "200", food),  # ነሐሴ 1
    ):
        setup.expenses.add(
            Expense.record(
                owner_id=owner.id,
                category_id=category.id,
                amount=Money.from_major(amount),
                spent_on=SpendDate.from_gregorian(day),
            )
        )
    setup.commit()
    return owner, food, transport


def test_listing_expenses_within_an_ethiopian_month(uow_factory, owner_with_expenses):
    owner, _, _ = owner_with_expenses
    first, last = HAMLE_2018.gregorian_span
    reader = uow_factory()
    criteria = ExpenseFilter(owner_id=owner.id, since=first, until=last)

    found = reader.expenses.list(criteria)
    assert len(found) == 3  # the 7 August expense belongs to ነሐሴ
    assert reader.expenses.count(criteria) == 3
    assert [e.spent_on.gregorian for e in found] == [
        date(2026, 8, 6),
        date(2026, 7, 22),
        date(2026, 7, 8),
    ]  # newest first


def test_filtering_by_category_and_paginating(uow_factory, owner_with_expenses):
    owner, food, _ = owner_with_expenses
    reader = uow_factory()
    criteria = ExpenseFilter(owner_id=owner.id, category_ids=(food.id,))
    assert reader.expenses.count(criteria) == 3

    page = ExpenseFilter(owner_id=owner.id, category_ids=(food.id,), limit=2)
    assert len(reader.expenses.list(page)) == 2
    second_page = ExpenseFilter(owner_id=owner.id, category_ids=(food.id,), limit=2, offset=2)
    assert len(reader.expenses.list(second_page)) == 1


def test_count_for_category_decides_archive_versus_delete(uow_factory, owner_with_expenses):
    owner, food, transport = owner_with_expenses
    reader = uow_factory()
    assert reader.expenses.count_for_category(owner.id, food.id) == 3
    assert reader.expenses.count_for_category(owner.id, transport.id) == 1
    assert reader.expenses.count_for_category(owner.id, CategoryId.new()) == 0


def test_editing_and_deleting_an_expense(uow_factory, owner_with_expenses):
    owner, food, _ = owner_with_expenses
    reader = uow_factory()
    expense = reader.expenses.list(ExpenseFilter(owner_id=owner.id, limit=1))[0]
    expense_id = expense.id
    expense.change_amount(Money.from_major("999"))
    reader.commit()

    checker = uow_factory()
    assert checker.expenses.get(owner.id, expense_id).amount == Money.from_major("999")
    checker.expenses.remove(checker.expenses.get(owner.id, expense_id))
    checker.commit()

    with pytest.raises(ExpenseNotFound):
        uow_factory().expenses.get(owner.id, expense_id)


def test_missing_expense_and_commitment_raise(uow):
    with pytest.raises(ExpenseNotFound):
        uow.expenses.get(OwnerId.new(), ExpenseId.new())
    with pytest.raises(FixedExpenseNotFound):
        uow.fixed_expenses.get(OwnerId.new(), FixedExpenseId.new())


# -- FixedExpense repository -------------------------------------------


@pytest.fixture
def owner_with_commitment(uow_factory):
    setup = uow_factory()
    owner = an_owner()
    setup.owners.add(owner)
    category = a_category(owner)
    setup.categories.add(category)
    commitment = FixedExpense.schedule(
        owner_id=owner.id,
        category_id=category.id,
        title="House rent",
        amount=Money.from_major("8000"),
        start_period=HAMLE_2018,
        due_day=5,
    )
    setup.fixed_expenses.add(commitment)
    setup.commit()
    return owner, category, commitment.id


def test_settling_through_the_repository_persists_the_settlement(
    uow_factory, owner_with_commitment
):
    owner, _, commitment_id = owner_with_commitment

    settler = uow_factory()
    settler.fixed_expenses.get(owner.id, commitment_id).settle(
        HAMLE_2018, settled_on=date(2026, 7, 12)
    )
    settler.commit()

    reader = uow_factory()
    reloaded = reader.fixed_expenses.get(owner.id, commitment_id)
    assert reloaded.is_settled_in(HAMLE_2018)
    assert reloaded.occurrence_for(HAMLE_2018).is_settled
    assert reloaded.occurrence_for(NEHASE_2018).is_outstanding


def test_unsettling_through_the_repository_removes_it(uow_factory, owner_with_commitment):
    owner, _, commitment_id = owner_with_commitment
    settler = uow_factory()
    settler.fixed_expenses.get(owner.id, commitment_id).settle(
        HAMLE_2018, settled_on=date(2026, 7, 12)
    )
    settler.commit()

    undoer = uow_factory()
    undoer.fixed_expenses.get(owner.id, commitment_id).unsettle(HAMLE_2018)
    undoer.commit()

    assert not uow_factory().fixed_expenses.get(owner.id, commitment_id).is_settled_in(HAMLE_2018)


def test_pausing_hides_a_commitment_from_the_active_list(uow_factory, owner_with_commitment):
    owner, _, commitment_id = owner_with_commitment
    pauser = uow_factory()
    pauser.fixed_expenses.get(owner.id, commitment_id).pause()
    pauser.commit()

    reader = uow_factory()
    assert reader.fixed_expenses.list_for_owner(owner.id, include_paused=False) == []
    assert len(reader.fixed_expenses.list_for_owner(owner.id)) == 1


def test_count_for_category_covers_commitments(uow_factory, owner_with_commitment):
    owner, category, _ = owner_with_commitment
    reader = uow_factory()
    assert reader.fixed_expenses.count_for_category(owner.id, category.id) == 1
    assert reader.fixed_expenses.count_for_category(owner.id, CategoryId.new()) == 0


# -- events -------------------------------------------------------------


def test_events_are_published_after_commit(uow_factory, event_bus):
    seen: list[str] = []
    event_bus.subscribe(OwnerRegistered, lambda event: seen.append(event.name))
    event_bus.subscribe(ExpenseRecorded, lambda event: seen.append(event.name))

    uow = uow_factory()
    owner = an_owner()
    uow.owners.add(owner)
    category = a_category(owner)
    uow.categories.add(category)
    uow.expenses.add(
        Expense.record(
            owner_id=owner.id,
            category_id=category.id,
            amount=Money.from_major("10"),
            spent_on=SpendDate.from_gregorian(date(2026, 7, 8)),
        )
    )
    assert seen == []  # nothing before the commit

    uow.commit()
    assert seen == ["OwnerRegistered", "ExpenseRecorded"]
    assert [e.name for e in uow.published_events] == seen


def test_no_events_are_published_when_the_transaction_rolls_back(uow_factory, event_bus):
    seen: list[str] = []
    event_bus.subscribe(OwnerRegistered, lambda event: seen.append(event.name))

    uow = uow_factory()
    uow.owners.add(an_owner())
    uow.rollback()
    assert seen == []
    assert uow.published_events == ()


def test_events_are_only_published_once(uow_factory, event_bus):
    seen: list[str] = []
    event_bus.subscribe(OwnerRegistered, lambda event: seen.append(event.name))

    uow = uow_factory()
    uow.owners.add(an_owner())
    uow.commit()
    uow.commit()  # a second commit has nothing new to say
    assert seen == ["OwnerRegistered"]


def test_a_failing_handler_does_not_hide_itself(uow_factory, event_bus):
    def explode(_event):
        raise RuntimeError("subscriber is broken")

    event_bus.subscribe(OwnerRegistered, explode)
    uow = uow_factory()
    uow.owners.add(an_owner())
    with pytest.raises(RuntimeError):
        uow.commit()
