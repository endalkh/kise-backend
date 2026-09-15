"""Every aggregate must survive a real database round trip with its value objects intact.

These tests are the safety net for the two-model-plus-mapper choice: if a mapper drops a field or
mangles a value object, the aggregate that comes back will not equal the one that went in.
"""

from __future__ import annotations

from datetime import UTC, date, datetime
from uuid import uuid4

import pytest
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from kise.expense_tracking.domain.models import (
    Category,
    Expense,
    FixedExpense,
    default_categories_for,
)
from kise.expense_tracking.domain.value_objects import PaymentMethod
from kise.expense_tracking.infrastructure.persistence.mappers import (
    CategoryMapper,
    ExpenseMapper,
    FixedExpenseMapper,
)
from kise.expense_tracking.infrastructure.persistence.models import (
    CategoryModel,
    ExpenseModel,
    FixedExpenseModel,
    SettlementModel,
)
from kise.identity.domain.models import EmailAddress, Owner, PasswordHash, Preferences
from kise.identity.infrastructure.persistence.mappers import OwnerMapper
from kise.identity.infrastructure.persistence.models import OwnerModel
from kise.platform.database import build_engine, build_session_factory, create_all
from kise.shared_kernel.domain.calendar import CalendarKind, Period, SpendDate
from kise.shared_kernel.domain.identifiers import OwnerId
from kise.shared_kernel.domain.money import Money

NOW = datetime(2026, 9, 4, 20, 0, tzinfo=UTC)
HAMLE_2018 = Period(CalendarKind.ETHIOPIAN, 2018, 11)
NEHASE_2018 = Period(CalendarKind.ETHIOPIAN, 2018, 12)


@pytest.fixture
def session():
    engine = build_engine("sqlite://")
    create_all(engine)
    factory = build_session_factory(engine)
    with factory() as open_session:
        yield open_session
    engine.dispose()


@pytest.fixture
def owner(session) -> Owner:
    aggregate = Owner.register(
        email=EmailAddress("selam@example.com"),
        password_hash=PasswordHash("$2b$12$hash"),
        display_name="Selam Tesfaye",
        registered_at=NOW,
        preferences=Preferences(calendar="ethiopian", language="am", currency="ETB"),
    )
    session.add(OwnerMapper.to_model(aggregate))
    session.commit()
    return aggregate


@pytest.fixture
def category(session, owner) -> Category:
    aggregate = Category.create(owner_id=owner.id, name="Rent", name_am="ቤት ኪራይ", color="#6D4C41")
    session.add(CategoryMapper.to_model(aggregate))
    session.commit()
    return aggregate


# -- Owner --------------------------------------------------------------


def test_owner_round_trip(session, owner):
    entity = session.get(OwnerModel, owner.id.value)
    restored = OwnerMapper.to_domain(entity)

    assert restored.id == owner.id
    assert restored.email == owner.email
    assert restored.display_name == owner.display_name
    assert restored.preferences == owner.preferences
    assert restored.password_hash == owner.password_hash
    # Rehydration is not an event: loading an Owner must not re-announce the registration.
    assert restored.pull_events() == []


def test_owner_update_is_written_back(session, owner):
    entity = session.get(OwnerModel, owner.id.value)
    restored = OwnerMapper.to_domain(entity)
    restored.prefer_calendar("gregorian")
    restored.rename("Selam T.")
    OwnerMapper.update_model(entity, restored)
    session.commit()

    reloaded = OwnerMapper.to_domain(session.get(OwnerModel, owner.id.value))
    assert reloaded.preferences.calendar is CalendarKind.GREGORIAN
    assert reloaded.display_name == "Selam T."


def test_duplicate_email_is_refused_by_the_schema(session, owner):
    clash = Owner.register(
        email=EmailAddress("selam@example.com"),
        password_hash=PasswordHash("$2b$12$other"),
        display_name="Someone Else",
        registered_at=NOW,
    )
    session.add(OwnerMapper.to_model(clash))
    with pytest.raises(IntegrityError):
        session.commit()


# -- Category -----------------------------------------------------------


def test_category_round_trip(session, category):
    restored = CategoryMapper.to_domain(session.get(CategoryModel, category.id.value))
    assert restored.id == category.id
    assert restored.name == "Rent"
    assert restored.name_am == "ቤት ኪራይ"
    assert restored.color == category.color
    assert restored.label("am") == "ቤት ኪራይ"
    assert not restored.is_archived


def test_archiving_is_persisted(session, category):
    entity = session.get(CategoryModel, category.id.value)
    restored = CategoryMapper.to_domain(entity)
    restored.archive()
    CategoryMapper.update_model(entity, restored)
    session.commit()

    assert CategoryMapper.to_domain(session.get(CategoryModel, category.id.value)).is_archived


def test_category_names_are_unique_per_owner_case_insensitively(session, owner, category):
    clash = Category.create(owner_id=owner.id, name="  rent ")
    session.add(CategoryMapper.to_model(clash))
    with pytest.raises(IntegrityError):
        session.commit()


def test_the_same_name_is_fine_for_a_different_owner(session, owner, category):
    other = Owner.register(
        email=EmailAddress("abebe@example.com"),
        password_hash=PasswordHash("$2b$12$hash"),
        display_name="Abebe",
        registered_at=NOW,
    )
    session.add(OwnerMapper.to_model(other))
    # Flush the Owner before adding a Category that points at it. Aggregate roots are not linked
    # by ORM relationships (crossing an aggregate boundary is done by id), so SQLAlchemy has no
    # dependency to order these inserts by — the repository controls the order instead.
    session.flush()
    session.add(CategoryMapper.to_model(Category.create(owner_id=other.id, name="Rent")))
    session.commit()

    stored = session.scalars(select(CategoryModel).where(CategoryModel.name == "Rent")).all()
    assert len(stored) == 2
    assert {row.owner_id for row in stored} == {owner.id.value, other.id.value}


def test_a_category_cannot_point_at_a_missing_owner(session):
    """The FK is real: orphan rows are refused rather than silently accepted."""
    session.add(CategoryMapper.to_model(Category.create(owner_id=OwnerId.new(), name="Ghost")))
    with pytest.raises(IntegrityError):
        session.commit()


def test_all_default_categories_persist(session, owner):
    session.add_all(CategoryMapper.to_model(c) for c in default_categories_for(owner.id))
    session.commit()
    stored = session.scalars(
        select(CategoryModel).where(CategoryModel.owner_id == owner.id.value)
    ).all()
    assert len(stored) == 10
    assert all(row.is_default for row in stored)
    assert all(row.name_am for row in stored)


# -- Expense ------------------------------------------------------------


def test_expense_round_trip_keeps_money_and_the_entry_calendar(session, owner, category):
    expense = Expense.record(
        owner_id=owner.id,
        category_id=category.id,
        amount=Money.from_major("1250.75"),
        spent_on=SpendDate.from_ethiopian(2018, 11, 15),
        note="ታክሲ",
        payment_method="telebirr",
    )
    session.add(ExpenseMapper.to_model(expense))
    session.commit()

    restored = ExpenseMapper.to_domain(session.get(ExpenseModel, expense.id.value))
    assert restored.amount == Money.from_major("1250.75")
    assert restored.amount.minor_units == 125075  # integer, no float anywhere
    assert restored.spent_on.gregorian == date(2026, 7, 22)
    assert restored.spent_on.entered_in is CalendarKind.ETHIOPIAN
    assert restored.spent_on.ethiopian.iso == "2018-11-15"
    assert restored.note == "ታክሲ"
    assert restored.payment_method is PaymentMethod.TELEBIRR
    assert restored.pull_events() == []


def test_expense_edits_are_written_back(session, owner, category):
    expense = Expense.record(
        owner_id=owner.id,
        category_id=category.id,
        amount=Money.from_major("100"),
        spent_on=SpendDate.from_gregorian(date(2026, 7, 1)),
    )
    entity = ExpenseMapper.to_model(expense)
    session.add(entity)
    session.commit()

    restored = ExpenseMapper.to_domain(entity)
    restored.change_amount(Money.from_major("150.25"))
    restored.move_to(SpendDate.from_ethiopian(2018, 12, 1))
    restored.amend_note("corrected")
    ExpenseMapper.update_model(entity, restored)
    session.commit()

    reloaded = ExpenseMapper.to_domain(session.get(ExpenseModel, expense.id.value))
    assert reloaded.amount == Money.from_major("150.25")
    assert reloaded.spent_on.ethiopian.iso == "2018-12-01"
    assert reloaded.note == "corrected"


# -- FixedExpense + Settlements ----------------------------------------


def a_commitment(owner, category, **overrides) -> FixedExpense:
    kwargs = {
        "owner_id": owner.id,
        "category_id": category.id,
        "title": "House rent",
        "amount": Money.from_major("8000"),
        "start_period": HAMLE_2018,
        "due_day": 5,
        "note": "Paid to Ato Bekele",
    }
    kwargs.update(overrides)
    return FixedExpense.schedule(**kwargs)


def test_fixed_expense_round_trip(session, owner, category):
    commitment = a_commitment(owner, category, end_period=Period(CalendarKind.ETHIOPIAN, 2019, 13))
    session.add(FixedExpenseMapper.to_model(commitment))
    session.commit()

    restored = FixedExpenseMapper.to_domain(session.get(FixedExpenseModel, commitment.id.value))
    assert restored.id == commitment.id
    assert restored.amount == Money.from_major("8000")
    assert restored.anchor_calendar is CalendarKind.ETHIOPIAN
    assert restored.start_period == HAMLE_2018
    assert restored.end_period == Period(CalendarKind.ETHIOPIAN, 2019, 13)
    assert restored.due_day.value == 5
    assert restored.note == "Paid to Ato Bekele"
    assert not restored.is_paused
    assert restored.pull_events() == []
    # And the rehydrated aggregate still computes Occurrences correctly.
    assert restored.occurrence_for(HAMLE_2018).due_date == date(2026, 7, 12)


def test_open_ended_commitment_stores_null_end(session, owner, category):
    commitment = a_commitment(owner, category)
    session.add(FixedExpenseMapper.to_model(commitment))
    session.commit()

    entity = session.get(FixedExpenseModel, commitment.id.value)
    assert entity.end_year is None and entity.end_month is None
    assert FixedExpenseMapper.to_domain(entity).is_open_ended


def test_settlements_are_persisted_with_the_aggregate(session, owner, category):
    commitment = a_commitment(owner, category)
    commitment.settle(HAMLE_2018, settled_on=date(2026, 7, 12))
    commitment.settle(NEHASE_2018, settled_on=date(2026, 8, 9), amount=Money.from_major("8200"))
    session.add(FixedExpenseMapper.to_model(commitment))
    session.commit()

    restored = FixedExpenseMapper.to_domain(session.get(FixedExpenseModel, commitment.id.value))
    assert len(restored.settlements) == 2
    assert restored.is_settled_in(HAMLE_2018)
    # The Settlement's Period comes back in the Anchor Calendar, not as bare integers.
    assert restored.settlement_for(NEHASE_2018).period == NEHASE_2018
    assert restored.occurrence_for(NEHASE_2018).amount == Money.from_major("8200")
    assert restored.occurrence_for(HAMLE_2018).amount == Money.from_major("8000")


def test_settling_after_load_inserts_a_child_row(session, owner, category):
    commitment = a_commitment(owner, category)
    entity = FixedExpenseMapper.to_model(commitment)
    session.add(entity)
    session.commit()

    restored = FixedExpenseMapper.to_domain(entity)
    restored.settle(HAMLE_2018, settled_on=date(2026, 7, 12))
    FixedExpenseMapper.update_model(entity, restored)
    session.commit()

    rows = session.scalars(select(SettlementModel)).all()
    assert len(rows) == 1
    assert (rows[0].period_year, rows[0].period_month) == (2018, 11)
    assert rows[0].amount_minor == 800000


def test_unsettling_after_load_deletes_the_child_row(session, owner, category):
    commitment = a_commitment(owner, category)
    commitment.settle(HAMLE_2018, settled_on=date(2026, 7, 12))
    entity = FixedExpenseMapper.to_model(commitment)
    session.add(entity)
    session.commit()
    assert len(session.scalars(select(SettlementModel)).all()) == 1

    restored = FixedExpenseMapper.to_domain(entity)
    restored.unsettle(HAMLE_2018)
    FixedExpenseMapper.update_model(entity, restored)
    session.commit()

    assert session.scalars(select(SettlementModel)).all() == []
    assert not FixedExpenseMapper.to_domain(entity).is_settled_in(HAMLE_2018)


def test_correcting_a_settlement_updates_the_child_row_in_place(session, owner, category):
    commitment = a_commitment(owner, category)
    settlement = commitment.settle(HAMLE_2018, settled_on=date(2026, 7, 12))
    entity = FixedExpenseMapper.to_model(commitment)
    session.add(entity)
    session.commit()

    restored = FixedExpenseMapper.to_domain(entity)
    restored.correct_settlement(
        HAMLE_2018, amount=Money.from_major("8100"), settled_on=date(2026, 7, 14)
    )
    FixedExpenseMapper.update_model(entity, restored)
    session.commit()

    rows = session.scalars(select(SettlementModel)).all()
    assert len(rows) == 1  # updated, not replaced
    assert rows[0].id == settlement.id.value
    assert rows[0].amount_minor == 810000
    assert rows[0].settled_on == date(2026, 7, 14)


def test_one_settlement_per_period_is_backstopped_by_the_schema(session, owner, category):
    """The aggregate refuses this first; the constraint is the second line of defence."""
    commitment = a_commitment(owner, category)
    commitment.settle(HAMLE_2018, settled_on=date(2026, 7, 12))
    entity = FixedExpenseMapper.to_model(commitment)
    session.add(entity)
    session.commit()

    session.add(
        SettlementModel(
            id=uuid4(),
            fixed_expense_id=commitment.id.value,
            owner_id=owner.id.value,
            period_year=2018,
            period_month=11,
            amount_minor=1,
            currency="ETB",
            settled_on=date(2026, 7, 13),
        )
    )
    with pytest.raises(IntegrityError):
        session.commit()


def test_deleting_a_commitment_takes_its_settlements(session, owner, category):
    commitment = a_commitment(owner, category)
    commitment.settle(HAMLE_2018, settled_on=date(2026, 7, 12))
    entity = FixedExpenseMapper.to_model(commitment)
    session.add(entity)
    session.commit()

    session.delete(entity)
    session.commit()
    assert session.scalars(select(SettlementModel)).all() == []


def test_pausing_and_editing_are_written_back(session, owner, category):
    commitment = a_commitment(owner, category)
    entity = FixedExpenseMapper.to_model(commitment)
    session.add(entity)
    session.commit()

    restored = FixedExpenseMapper.to_domain(entity)
    restored.pause()
    restored.change_amount(Money.from_major("9000"))
    restored.change_due_day(28)
    restored.end_after(NEHASE_2018)
    FixedExpenseMapper.update_model(entity, restored)
    session.commit()

    reloaded = FixedExpenseMapper.to_domain(session.get(FixedExpenseModel, commitment.id.value))
    assert reloaded.is_paused
    assert reloaded.amount == Money.from_major("9000")
    assert reloaded.due_day.value == 28
    assert reloaded.end_period == NEHASE_2018


def test_a_gregorian_anchored_commitment_keeps_its_calendar(session, owner, category):
    commitment = a_commitment(
        owner, category, start_period=Period(CalendarKind.GREGORIAN, 2026, 1)
    )
    session.add(FixedExpenseMapper.to_model(commitment))
    session.commit()

    restored = FixedExpenseMapper.to_domain(session.get(FixedExpenseModel, commitment.id.value))
    assert restored.anchor_calendar is CalendarKind.GREGORIAN
    assert restored.start_period == Period(CalendarKind.GREGORIAN, 2026, 1)
