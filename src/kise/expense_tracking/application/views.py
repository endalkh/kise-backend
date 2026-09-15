"""What the Expense Tracking services return.

Views are plain, already-resolved data: the category name is filled in, money is a ``Money``, a date
is a ``SpendDate`` that can render itself in either calendar. The presentation layer only has to
serialise them, and never reaches back into an aggregate to ask a follow-up question.

Each has an ``of(...)`` constructor that takes the aggregate, so the mapping lives in one place
rather than being repeated in every service method.

What the services *accept* lives in ``commands.py``.
"""


from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date

from kise.expense_tracking.domain.models import (
    Category,
    Expense,
    FixedExpense,
    Item,
    Occurrence,
    Quantity,
    UnitOfMeasurement,
)
from kise.shared_kernel.domain.calendar.calendar_kind import CalendarKind
from kise.shared_kernel.domain.calendar.period import Period
from kise.shared_kernel.domain.calendar.spend_date import SpendDate
from kise.shared_kernel.domain.identifiers import (
    CategoryId,
    ExpenseId,
    FixedExpenseId,
    ItemId,
    UnitId,
)
from kise.shared_kernel.domain.money import Money


@dataclass(frozen=True, slots=True)
class CategoryView:
    category_id: CategoryId
    name: str
    name_am: str | None
    color: str
    icon: str | None
    is_archived: bool
    is_default: bool

    @classmethod
    def of(cls, category: Category) -> CategoryView:
        return cls(
            category_id=category.id,
            name=category.name,
            name_am=category.name_am,
            color=category.color.value,
            icon=category.icon,
            is_archived=category.is_archived,
            is_default=category.is_default,
        )


@dataclass(frozen=True, slots=True)
class ExpenseView:
    expense_id: ExpenseId
    category_id: CategoryId
    amount: Money
    spent_on: SpendDate
    note: str | None
    payment_method: str
    category_name: str | None = None
    category_name_am: str | None = None
    item_id: ItemId | None = None
    item_name: str | None = None
    item_name_am: str | None = None
    quantity: Quantity | None = None
    unit_id: UnitId | None = None
    unit_code: str | None = None
    unit_name: str | None = None
    unit_name_am: str | None = None

    @classmethod
    def of(
        cls,
        expense: Expense,
        category: Category | None = None,
        item: Item | None = None,
        unit: UnitOfMeasurement | None = None,
    ) -> ExpenseView:
        return cls(
            expense_id=expense.id,
            category_id=expense.category_id,
            amount=expense.amount,
            spent_on=expense.spent_on,
            note=expense.note,
            payment_method=expense.payment_method.value,
            category_name=category.name if category else None,
            category_name_am=category.name_am if category else None,
            item_id=expense.item_id,
            item_name=item.name if item else None,
            item_name_am=item.name_am if item else None,
            quantity=expense.quantity,
            unit_id=expense.unit_id,
            unit_code=unit.code if unit else None,
            unit_name=unit.name if unit else None,
            unit_name_am=unit.name_am if unit else None,
        )


@dataclass(frozen=True, slots=True)
class ExpensePage:
    """A page of expenses, with the total so the app can show "23 expenses"."""

    items: tuple[ExpenseView, ...]
    total: int
    limit: int
    offset: int
    total_amount: Money


@dataclass(frozen=True, slots=True)
class FixedExpenseView:
    fixed_expense_id: FixedExpenseId
    category_id: CategoryId
    title: str
    amount: Money
    anchor_calendar: CalendarKind
    start_period: Period
    end_period: Period | None
    due_day: int
    note: str | None
    is_paused: bool
    settled_periods: tuple[Period, ...] = field(default_factory=tuple)
    category_name: str | None = None
    category_name_am: str | None = None

    @classmethod
    def of(cls, commitment: FixedExpense, category: Category | None = None) -> FixedExpenseView:
        return cls(
            fixed_expense_id=commitment.id,
            category_id=commitment.category_id,
            title=commitment.title,
            amount=commitment.amount,
            anchor_calendar=commitment.anchor_calendar,
            start_period=commitment.start_period,
            end_period=commitment.end_period,
            due_day=commitment.due_day.value,
            note=commitment.note,
            is_paused=commitment.is_paused,
            settled_periods=tuple(s.period for s in commitment.settlements),
            category_name=category.name if category else None,
            category_name_am=category.name_am if category else None,
        )


@dataclass(frozen=True, slots=True)
class OccurrenceView:
    fixed_expense_id: FixedExpenseId
    category_id: CategoryId
    title: str
    period: Period
    due_date: date
    amount: Money
    is_settled: bool
    settled_on: date | None
    category_name: str | None = None
    category_name_am: str | None = None

    @classmethod
    def of(cls, occurrence: Occurrence, category: Category | None = None) -> OccurrenceView:
        return cls(
            fixed_expense_id=occurrence.fixed_expense_id,
            category_id=occurrence.category_id,
            title=occurrence.title,
            period=occurrence.period,
            due_date=occurrence.due_date,
            amount=occurrence.amount,
            is_settled=occurrence.is_settled,
            settled_on=occurrence.settled_on,
            category_name=category.name if category else None,
            category_name_am=category.name_am if category else None,
        )


@dataclass(frozen=True, slots=True)
class UnitView:
    unit_id: UnitId
    code: str
    name: str
    name_am: str | None
    is_system: bool

    @classmethod
    def of(cls, unit: UnitOfMeasurement) -> UnitView:
        return cls(
            unit_id=unit.id,
            code=unit.code,
            name=unit.name,
            name_am=unit.name_am,
            is_system=unit.is_system,
        )


@dataclass(frozen=True, slots=True)
class ItemView:
    item_id: ItemId
    name: str
    name_am: str | None
    default_unit_id: UnitId | None
    is_archived: bool

    @classmethod
    def of(cls, item: Item) -> ItemView:
        return cls(
            item_id=item.id,
            name=item.name,
            name_am=item.name_am,
            default_unit_id=item.default_unit_id,
            is_archived=item.is_archived,
        )


@dataclass(frozen=True, slots=True)
class ItemUsageLine:
    """One row of the month-end report: how much of an item was bought, in one unit.

    Grouped by (item, unit), because "3 kg + 2 pcs of onions" cannot be added — the unit is what
    makes the total meaningful. ``total_amount`` is the money spent on that item-in-that-unit.
    """

    item_id: ItemId
    item_name: str
    item_name_am: str | None
    unit_id: UnitId
    unit_code: str
    unit_name: str
    unit_name_am: str | None
    total_quantity: Quantity
    total_amount: Money
    entry_count: int


@dataclass(frozen=True, slots=True)
class ItemUsageReport:
    """The whole month's item usage, one line per (item, unit)."""

    period: Period
    lines: tuple[ItemUsageLine, ...]
    currency: str
