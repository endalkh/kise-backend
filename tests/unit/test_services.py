"""Application services, tested with in-memory fakes and no database.

This module also settles a worry raised by dropping the abstract repository ports: without an
interface to implement, can a service still be tested in isolation? Yes — Python is duck typed,
so a fake needs the right methods and nothing else. What is lost is the compiler-checked
promise that a fake and the real repository agree. Standing in for it is the integration
suite, which runs the same services against real SQLite.
"""

from __future__ import annotations

from dataclasses import replace
from datetime import UTC, date, datetime

import pytest

from kise.expense_tracking.application.commands import (
    CreateCategoryCommand,
    DateInput,
    ListExpensesQuery,
    PeriodInput,
    RecordExpenseCommand,
    UpdateCategoryCommand,
    UpdateExpenseCommand,
)
from kise.expense_tracking.application.services import CategoryService, ExpenseService
from kise.expense_tracking.domain.errors import (
    CategoryArchived,
    CategoryNameTaken,
    CategoryNotFound,
    ExpenseNotFound,
)
from kise.expense_tracking.domain.models import Category
from kise.identity.application.commands import (
    AuthenticateOwnerCommand,
    RegisterOwnerCommand,
    UpdatePreferencesCommand,
)
from kise.identity.application.services import OwnerService
from kise.identity.domain.errors import (
    EmailAlreadyRegistered,
    InvalidCredentials,
    OwnerNotFound,
)
from kise.identity.domain.models import PasswordHash
from kise.shared_kernel.domain.calendar import CalendarKind
from kise.shared_kernel.domain.errors import ValidationError
from kise.shared_kernel.domain.identifiers import CategoryId, ExpenseId, OwnerId
from kise.shared_kernel.domain.money import Money

NOW = datetime(2026, 9, 4, 20, 0, tzinfo=UTC)


# -- fakes --------------------------------------------------------------


class FakeUnitOfWork:
    def __init__(self) -> None:
        self.commits = 0
        self.rollbacks = 0

    def commit(self) -> None:
        self.commits += 1

    def rollback(self) -> None:
        self.rollbacks += 1

    def flush(self) -> None:
        pass

    def register(self, participant) -> None:
        pass


class FakeOwners:
    def __init__(self) -> None:
        self.items: dict[OwnerId, object] = {}

    def add(self, owner) -> None:
        self.items[owner.id] = owner

    def get(self, owner_id):
        try:
            return self.items[owner_id]
        except KeyError:
            raise OwnerNotFound("No such account", owner_id=str(owner_id)) from None

    def find_by_email(self, email):
        return next((o for o in self.items.values() if o.email == email), None)

    def email_exists(self, email) -> bool:
        return self.find_by_email(email) is not None


class FakeCategories:
    def __init__(self) -> None:
        self.items: dict[CategoryId, Category] = {}
        self.removed: list[CategoryId] = []

    def add(self, category) -> None:
        self.items[category.id] = category

    def add_all(self, categories) -> None:
        for category in categories:
            self.add(category)

    def get(self, owner_id, category_id):
        found = self.items.get(category_id)
        if found is None or found.owner_id != owner_id:
            raise CategoryNotFound("No such category", category_id=str(category_id))
        return found

    def list_for_owner(self, owner_id, *, include_archived: bool = False):
        found = [c for c in self.items.values() if c.owner_id == owner_id]
        if not include_archived:
            found = [c for c in found if not c.is_archived]
        return sorted(found, key=lambda c: c.name)

    def remove(self, category) -> None:
        self.items.pop(category.id, None)
        self.removed.append(category.id)


class FakeExpenses:
    def __init__(self) -> None:
        self.items: dict[ExpenseId, object] = {}

    def add(self, expense) -> None:
        self.items[expense.id] = expense

    def get(self, owner_id, expense_id):
        found = self.items.get(expense_id)
        if found is None or found.owner_id != owner_id:
            raise ExpenseNotFound("No such expense", expense_id=str(expense_id))
        return found

    def _matching(self, criteria):
        found = [e for e in self.items.values() if e.owner_id == criteria.owner_id]
        if criteria.since:
            found = [e for e in found if e.spent_on.gregorian >= criteria.since]
        if criteria.until:
            found = [e for e in found if e.spent_on.gregorian <= criteria.until]
        if criteria.category_ids:
            found = [e for e in found if e.category_id in criteria.category_ids]
        return sorted(found, key=lambda e: e.spent_on.gregorian, reverse=True)

    def list(self, criteria):
        found = self._matching(criteria)
        return found[criteria.offset : criteria.offset + criteria.limit]

    def count(self, criteria) -> int:
        return len(self._matching(criteria))

    def count_for_category(self, owner_id, category_id) -> int:
        return len(
            [
                e
                for e in self.items.values()
                if e.owner_id == owner_id and e.category_id == category_id
            ]
        )

    def remove(self, expense) -> None:
        self.items.pop(expense.id, None)


class FakeFixedExpenses:
    def __init__(self) -> None:
        self.items: dict[object, object] = {}

    def count_for_category(self, owner_id, category_id) -> int:
        return len(
            [
                f
                for f in self.items.values()
                if f.owner_id == owner_id and f.category_id == category_id
            ]
        )


class FakeHasher:
    """Reversible on purpose: a test wants to see that hashing happened, not to be slow."""

    def hash(self, plaintext: str) -> PasswordHash:
        if len(plaintext) < 8:
            raise ValidationError("Password must be at least 8 characters", field="password")
        return PasswordHash(f"hashed::{plaintext}")

    def verify(self, plaintext: str, hashed: PasswordHash) -> bool:
        return hashed.value == f"hashed::{plaintext}"


class FakeTokens:
    def __init__(self) -> None:
        self.issued: list[OwnerId] = []

    def issue(self, owner_id: OwnerId):
        from kise.identity.application.ports import AccessToken

        self.issued.append(owner_id)
        return AccessToken(f"token-for-{owner_id}", NOW)

    def read(self, token: str) -> OwnerId:
        return OwnerId.parse(token.removeprefix("token-for-"))


class FakeClock:
    def now(self) -> datetime:
        return NOW

    def today(self) -> date:
        return NOW.date()


@pytest.fixture
def uow() -> FakeUnitOfWork:
    return FakeUnitOfWork()


@pytest.fixture
def owners() -> FakeOwners:
    return FakeOwners()


@pytest.fixture
def categories() -> FakeCategories:
    return FakeCategories()


@pytest.fixture
def expenses() -> FakeExpenses:
    return FakeExpenses()


# -- registration -------------------------------------------------------


@pytest.fixture
def owner_service(owners, uow) -> OwnerService:
    return OwnerService(owners, FakeHasher(), FakeTokens(), FakeClock(), uow)


@pytest.fixture
def category_service(categories, expenses, uow) -> CategoryService:
    return CategoryService(categories, expenses, FakeFixedExpenses(), uow)


@pytest.fixture
def expense_service(expenses, categories, uow) -> ExpenseService:
    return ExpenseService(expenses, categories, uow)


def test_registering_returns_a_profile_and_a_token(owner_service, uow):
    result = owner_service.register(
        RegisterOwnerCommand(
            email="Selam@Example.com", password="a good password", display_name="  Selam  Tesfaye "
        )
    )
    assert result.profile.email == "selam@example.com"  # normalised
    assert result.profile.display_name == "Selam Tesfaye"  # whitespace collapsed
    assert result.profile.calendar is CalendarKind.ETHIOPIAN  # Kise's default
    assert result.profile.currency == "ETB"
    assert result.token.value.startswith("token-for-")
    assert result.profile.registered_at == NOW  # from the Clock, not the wall clock
    assert uow.commits == 1


def test_the_password_is_hashed_before_it_is_stored(owner_service, owners):
    owner_service.register(
        RegisterOwnerCommand(
            email="selam@example.com", password="a good password", display_name="Selam"
        )
    )
    stored = next(iter(owners.items.values()))
    assert stored.password_hash.value == "hashed::a good password"


def test_registering_twice_with_the_same_email_is_refused(owner_service, uow):
    command = RegisterOwnerCommand(
        email="selam@example.com", password="a good password", display_name="Selam"
    )
    owner_service.register(command)
    with pytest.raises(EmailAlreadyRegistered):
        owner_service.register(replace(command, display_name="Someone"))
    assert uow.commits == 1  # the second attempt committed nothing


def test_registration_honours_chosen_preferences(owner_service):
    result = owner_service.register(
        RegisterOwnerCommand(
            email="abebe@example.com",
            password="a good password",
            display_name="Abebe",
            calendar="gregorian",
            language="en",
            currency="usd",
        )
    )
    assert result.profile.calendar is CalendarKind.GREGORIAN
    assert result.profile.currency == "USD"


def test_a_bad_email_or_short_password_never_reaches_the_repository(owner_service, owners, uow):
    with pytest.raises(ValidationError):
        owner_service.register(
            RegisterOwnerCommand(email="nope", password="a good password", display_name="X")
        )
    with pytest.raises(ValidationError):
        owner_service.register(
            RegisterOwnerCommand(email="ok@example.com", password="short", display_name="X")
        )
    assert owners.items == {}
    assert uow.commits == 0


# -- signing in ---------------------------------------------------------


def test_signing_in_with_the_right_password(owner_service):
    owner_service.register(
        RegisterOwnerCommand(
            email="selam@example.com", password="a good password", display_name="Selam"
        )
    )
    result = owner_service.authenticate(
        AuthenticateOwnerCommand(email="SELAM@example.com", password="a good password")
    )
    assert result.profile.email == "selam@example.com"


@pytest.mark.parametrize(
    ("email", "password"),
    [
        ("selam@example.com", "the wrong password"),
        ("nobody@example.com", "a good password"),
        ("not-an-email", "a good password"),
    ],
)
def test_every_failed_sign_in_looks_identical(owner_service, email, password):
    """Wrong password, unknown account and malformed email must be indistinguishable, or the
    endpoint becomes a way to discover who has an account."""
    owner_service.register(
        RegisterOwnerCommand(
            email="selam@example.com", password="a good password", display_name="Selam"
        )
    )
    with pytest.raises(InvalidCredentials):
        owner_service.authenticate(
            AuthenticateOwnerCommand(email=email, password=password)
        )


# -- profile ------------------------------------------------------------


def test_reading_and_updating_the_profile(owner_service):
    registered = owner_service.register(
        RegisterOwnerCommand(
            email="selam@example.com", password="a good password", display_name="Selam"
        )
    )
    owner_id = registered.profile.owner_id

    assert owner_service.profile(owner_id).display_name == "Selam"

    updated = owner_service.update_preferences(
        UpdatePreferencesCommand(
            owner_id=owner_id, display_name="Selam T.", calendar="gregorian", language="en"
        )
    )
    assert updated.display_name == "Selam T."
    assert updated.calendar is CalendarKind.GREGORIAN
    assert owner_service.profile(owner_id).language.value == "en"


def test_reading_a_missing_profile(owner_service):
    with pytest.raises(OwnerNotFound):
        owner_service.profile(OwnerId.new())


# -- categories ---------------------------------------------------------

OWNER = OwnerId.new()


def test_creating_a_category(uow, category_service):
    view = category_service.create(
        CreateCategoryCommand(owner_id=OWNER, name="  Coffee ", name_am="ቡና", color="#6f4e37")
    )
    assert view.name == "Coffee"
    assert view.name_am == "ቡና"
    assert view.color == "#6F4E37"
    assert uow.commits == 1


def test_duplicate_category_names_are_refused_case_insensitively(uow, category_service):
    create = category_service.create
    create(CreateCategoryCommand(owner_id=OWNER, name="Food"))
    with pytest.raises(CategoryNameTaken):
        create(CreateCategoryCommand(owner_id=OWNER, name="  food "))
    assert uow.commits == 1


def test_an_archived_category_still_blocks_the_name(category_service):
    """Reusing an archived category's name would make two rows indistinguishable in a report."""
    create = category_service.create
    view = create(CreateCategoryCommand(owner_id=OWNER, name="Food"))
    category_service.archive(OWNER, view.category_id)
    with pytest.raises(CategoryNameTaken):
        create(CreateCategoryCommand(owner_id=OWNER, name="food"))


def test_another_owner_may_reuse_a_name(category_service):
    create = category_service.create
    create(CreateCategoryCommand(owner_id=OWNER, name="Food"))
    other = create(CreateCategoryCommand(owner_id=OwnerId.new(), name="Food"))
    assert other.name == "Food"


def test_renaming_a_category_may_keep_its_own_name(category_service):
    view = category_service.create(
        CreateCategoryCommand(owner_id=OWNER, name="Food")
    )
    updated = category_service.update(
        UpdateCategoryCommand(
            owner_id=OWNER, category_id=view.category_id, name="FOOD", name_am="ምግብ"
        )
    )
    assert (updated.name, updated.name_am) == ("FOOD", "ምግብ")


def test_listing_hides_archived_categories(category_service):
    create = category_service.create
    food = create(CreateCategoryCommand(owner_id=OWNER, name="Food"))
    create(CreateCategoryCommand(owner_id=OWNER, name="Transport"))
    category_service.archive(OWNER, food.category_id)

    listing = category_service.list
    assert [c.name for c in listing(OWNER)] == ["Transport"]
    assert [c.name for c in listing(OWNER, include_archived=True)] == [
        "Food",
        "Transport",
    ]


def test_a_category_in_use_is_archived_instead_of_deleted(
    categories, category_service, expense_service
):
    """The rule that keeps last ሐምሌ's report readable."""
    category = category_service.create(
        CreateCategoryCommand(owner_id=OWNER, name="Food")
    )
    expense_service.record(
        RecordExpenseCommand(
            owner_id=OWNER,
            category_id=category.category_id,
            amount_minor=5000,
            spent_on=DateInput("2018-11-15", "ethiopian"),
        )
    )

    result = category_service.remove(
        OWNER, category.category_id
    )
    assert result is not None
    assert result.is_archived
    assert categories.removed == []  # nothing was deleted


def test_an_unused_category_is_deleted(categories, category_service):
    category = category_service.create(
        CreateCategoryCommand(owner_id=OWNER, name="Unused")
    )
    result = category_service.remove(
        OWNER, category.category_id
    )
    assert result is None
    assert categories.removed == [category.category_id]


def test_a_category_belonging_to_someone_else_is_invisible(category_service):
    category = category_service.create(
        CreateCategoryCommand(owner_id=OWNER, name="Food")
    )
    with pytest.raises(CategoryNotFound):
        category_service.archive(OwnerId.new(), category.category_id)


# -- expenses -----------------------------------------------------------


@pytest.fixture
def a_category(category_service) -> CategoryId:
    return category_service.create(
        CreateCategoryCommand(owner_id=OWNER, name="Food", name_am="ምግብ")
    ).category_id


def test_recording_an_expense_entered_in_the_ethiopian_calendar(expense_service, a_category):
    view = expense_service.record(
        RecordExpenseCommand(
            owner_id=OWNER,
            category_id=a_category,
            amount_minor=12050,
            spent_on=DateInput("2018-11-15", "ethiopian"),
            note="ሸይ ቡና",
            payment_method="telebirr",
        )
    )
    assert view.amount == Money(12050, "ETB")
    assert view.spent_on.gregorian == date(2026, 7, 22)
    assert view.spent_on.entered_in is CalendarKind.ETHIOPIAN
    assert view.category_name_am == "ምግብ"  # resolved for the app's label
    assert view.payment_method == "telebirr"


def test_the_same_day_in_either_calendar_is_stored_identically(expense_service, a_category):
    record = expense_service.record
    from_ethiopian = record(
        RecordExpenseCommand(
            owner_id=OWNER,
            category_id=a_category,
            amount_minor=100,
            spent_on=DateInput("2018-11-15", "ethiopian"),
        )
    )
    from_gregorian = record(
        RecordExpenseCommand(
            owner_id=OWNER,
            category_id=a_category,
            amount_minor=100,
            spent_on=DateInput("2026-07-22", "gregorian"),
        )
    )
    assert from_ethiopian.spent_on.gregorian == from_gregorian.spent_on.gregorian


def test_recording_against_an_archived_category_is_refused(
    expense_service, category_service, a_category
):
    category_service.archive(OWNER, a_category)
    with pytest.raises(CategoryArchived):
        expense_service.record(
            RecordExpenseCommand(
                owner_id=OWNER,
                category_id=a_category,
                amount_minor=100,
                spent_on=DateInput("2026-07-22"),
            )
        )


def test_recording_against_someone_elses_category_is_refused(a_category, expense_service):
    with pytest.raises(CategoryNotFound):
        expense_service.record(
            RecordExpenseCommand(
                owner_id=OwnerId.new(),
                category_id=a_category,
                amount_minor=100,
                spent_on=DateInput("2026-07-22"),
            )
        )


def test_updating_and_deleting_an_expense(expenses, a_category, expense_service):
    view = expense_service.record(
        RecordExpenseCommand(
            owner_id=OWNER,
            category_id=a_category,
            amount_minor=100,
            spent_on=DateInput("2026-07-22"),
        )
    )
    updated = expense_service.update(
        UpdateExpenseCommand(
            owner_id=OWNER,
            expense_id=view.expense_id,
            amount_minor=25050,
            spent_on=DateInput("2018-12-01", "ethiopian"),
            note="corrected",
        )
    )
    assert updated.amount == Money(25050, "ETB")
    assert updated.spent_on.ethiopian.iso == "2018-12-01"
    assert updated.note == "corrected"

    expense_service.delete(OWNER, view.expense_id)
    with pytest.raises(ExpenseNotFound):
        expenses.get(OWNER, view.expense_id)


def test_listing_expenses_for_an_ethiopian_period(a_category, expense_service):
    record = expense_service.record
    for day, amount in (
        ("2026-07-08", 1000),  # ሐምሌ 1
        ("2026-08-06", 2000),  # ሐምሌ 30
        ("2026-08-07", 4000),  # ነሐሴ 1 — outside
    ):
        record(
            RecordExpenseCommand(
                owner_id=OWNER,
                category_id=a_category,
                amount_minor=amount,
                spent_on=DateInput(day, "gregorian"),
            )
        )

    page = expense_service.list(
        ListExpensesQuery(owner_id=OWNER, period=PeriodInput(2018, 11, "ethiopian"))
    )
    assert page.total == 2
    assert page.total_amount == Money(3000, "ETB")
    assert [e.spent_on.gregorian for e in page.items] == [date(2026, 8, 6), date(2026, 7, 8)]


def test_listing_paginates_and_reports_the_full_total(a_category, expense_service):
    record = expense_service.record
    for day in range(1, 6):
        record(
            RecordExpenseCommand(
                owner_id=OWNER,
                category_id=a_category,
                amount_minor=1000,
                spent_on=DateInput(f"2026-07-0{day}", "gregorian"),
            )
        )

    page = expense_service.list(
        ListExpensesQuery(owner_id=OWNER, limit=2, offset=2)
    )
    assert len(page.items) == 2
    assert page.total == 5  # the count is of the filter, not of the page
    assert page.offset == 2
