"""What the Expense Tracking services accept.

Three kinds of thing live here, and all of them are *inputs*:

``DateInput`` / ``PeriodInput``   a value plus the calendar it is written in. This pair is why
                                 "ሐምሌ 15, 2018" and "22 July 2026" can reach the same service
                                 without either calendar being privileged — the service calls
                                 ``.resolve()`` and gets a ``SpendDate`` or a ``Period``.
``*Command``                     one per operation. They carry primitives, because they arrive from
                                 outside: an HTTP body, a CLI argument, a test. Turning primitives
                                 into value objects is the service's first job, so a bad amount or a
                                 nonexistent ጳጉሜን 6 is refused at the edge.
``ListExpensesQuery`` /          the read side. ``ListExpensesQuery`` is what a caller asks for, in
``ExpenseFilter``                either calendar; ``ExpenseFilter`` is what it resolves to, with
                                 Gregorian dates, because that is what storage holds.

Why these exist at all: without them a service method would take seven positional arguments, and
the only alternative — passing the HTTP request model straight through — would drag Pydantic and
the wire format into the application layer. A command is the contract, independent of the caller.

What the services *return* lives in ``views.py``.
"""


from __future__ import annotations

from dataclasses import dataclass
from datetime import date

from kise.shared_kernel.domain.calendar.calendar_kind import CalendarKind
from kise.shared_kernel.domain.calendar.period import Period
from kise.shared_kernel.domain.calendar.spend_date import SpendDate
from kise.shared_kernel.domain.identifiers import (
    CategoryId,
    ExpenseId,
    FixedExpenseId,
    ItemId,
    OwnerId,
    UnitId,
)

# -- inputs -------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class DateInput:
    """A date plus the calendar it is written in."""

    value: str
    calendar: CalendarKind | str = CalendarKind.GREGORIAN

    def resolve(self) -> SpendDate:
        return SpendDate.parse(self.value, self.calendar)


@dataclass(frozen=True, slots=True)
class PeriodInput:
    """A month plus the calendar it belongs to."""

    year: int
    month: int
    calendar: CalendarKind | str = CalendarKind.ETHIOPIAN

    def resolve(self) -> Period:
        return Period.of(self.calendar, self.year, self.month)


# -- category commands --------------------------------------------------


@dataclass(frozen=True, slots=True)
class CreateCategoryCommand:
    owner_id: OwnerId
    name: str
    name_am: str | None = None
    color: str | None = None
    icon: str | None = None


@dataclass(frozen=True, slots=True)
class UpdateCategoryCommand:
    owner_id: OwnerId
    category_id: CategoryId
    name: str | None = None
    name_am: str | None = None
    color: str | None = None
    icon: str | None = None


# -- expense commands ---------------------------------------------------


@dataclass(frozen=True, slots=True)
class ItemLineInput:
    """The optional 'what was bought' part of an expense.

    Either an existing item (``item_id``) or a new one to create on the fly (``item_name``), plus a
    quantity and the unit it is counted in. All fields ``None`` means no item line at all.
    """

    item_id: ItemId | None = None
    item_name: str | None = None
    item_name_am: str | None = None
    quantity: str | None = None  # a human amount like "1.5"; the service builds a Quantity
    unit_id: UnitId | None = None

    @property
    def is_present(self) -> bool:
        return any(
            v is not None
            for v in (self.item_id, self.item_name, self.quantity, self.unit_id)
        )


@dataclass(frozen=True, slots=True)
class RecordExpenseCommand:
    owner_id: OwnerId
    category_id: CategoryId
    amount_minor: int
    spent_on: DateInput
    note: str | None = None
    payment_method: str | None = None
    item: ItemLineInput | None = None


@dataclass(frozen=True, slots=True)
class UpdateExpenseCommand:
    owner_id: OwnerId
    expense_id: ExpenseId
    amount_minor: int | None = None
    category_id: CategoryId | None = None
    spent_on: DateInput | None = None
    note: str | None = None
    payment_method: str | None = None
    item: ItemLineInput | None = None
    clear_item: bool = False


@dataclass(frozen=True, slots=True)
class CreateUnitCommand:
    code: str
    name: str
    name_am: str | None = None


@dataclass(frozen=True, slots=True)
class CreateItemCommand:
    owner_id: OwnerId
    name: str
    name_am: str | None = None
    default_unit_id: UnitId | None = None


@dataclass(frozen=True, slots=True)
class ItemUsageQuery:
    """A month's item usage, in either calendar."""

    owner_id: OwnerId
    period: PeriodInput


@dataclass(frozen=True, slots=True)
class ExpenseFilter:
    """How a list of Expenses is narrowed, as the repository wants it.

    Dates are Gregorian because storage is. A ``ListExpensesQuery`` arrives from outside with a
    calendar attached; this is what it resolves to.
    """

    owner_id: OwnerId
    since: date | None = None
    until: date | None = None
    category_ids: tuple[CategoryId, ...] = ()
    limit: int = 50
    offset: int = 0


@dataclass(frozen=True, slots=True)
class ListExpensesQuery:
    owner_id: OwnerId
    since: DateInput | None = None
    until: DateInput | None = None
    period: PeriodInput | None = None
    category_ids: tuple[CategoryId, ...] = ()
    limit: int = 50
    offset: int = 0


# -- fixed expense commands --------------------------------------------


@dataclass(frozen=True, slots=True)
class ScheduleFixedExpenseCommand:
    owner_id: OwnerId
    category_id: CategoryId
    title: str
    amount_minor: int
    start_period: PeriodInput
    end_period: PeriodInput | None = None
    due_day: int = 1
    note: str | None = None


@dataclass(frozen=True, slots=True)
class UpdateFixedExpenseCommand:
    owner_id: OwnerId
    fixed_expense_id: FixedExpenseId
    title: str | None = None
    amount_minor: int | None = None
    category_id: CategoryId | None = None
    due_day: int | None = None
    note: str | None = None
    end_period: PeriodInput | None = None
    clear_end_period: bool = False


@dataclass(frozen=True, slots=True)
class SettleOccurrenceCommand:
    owner_id: OwnerId
    fixed_expense_id: FixedExpenseId
    period: PeriodInput
    settled_on: DateInput | None = None
    amount_minor: int | None = None


