"""The Expense aggregate — one recorded act of spending (a Dynamic Expense).

Small on purpose: an Expense has no children, so the aggregate boundary is the record itself. The
rules it owns are that the amount is positive, the note is bounded, and the date remembers which
calendar the Owner typed it in.
"""

from __future__ import annotations

from kise.expense_tracking.domain.events import ExpenseRecorded
from kise.expense_tracking.domain.value_objects.quantity import Quantity
from kise.expense_tracking.domain.value_objects.values import PaymentMethod, clean_note
from kise.shared_kernel.domain.calendar.calendar_kind import CalendarKind
from kise.shared_kernel.domain.calendar.period import Period
from kise.shared_kernel.domain.calendar.spend_date import SpendDate
from kise.shared_kernel.domain.entity import AggregateRoot
from kise.shared_kernel.domain.errors import InvariantViolation, ValidationError
from kise.shared_kernel.domain.identifiers import CategoryId, ExpenseId, ItemId, OwnerId, UnitId
from kise.shared_kernel.domain.money import Money


def _validate_item_line(
    item_id: ItemId | None, quantity: Quantity | None, unit_id: UnitId | None
) -> None:
    """The item line is all-or-nothing in its essentials.

    An expense may carry no item at all. But if it names an item, it must say how much and in what
    unit — "some sugar" is not a measurable fact. Quantity without an item is also rejected: a bare
    number is meaningless without knowing what it counts.
    """
    if item_id is None:
        if quantity is not None or unit_id is not None:
            raise ValidationError(
                "quantity and unit only make sense with an item", field="item_id"
            )
        return
    if quantity is None or unit_id is None:
        raise ValidationError(
            "an item expense needs both a quantity and a unit", field="quantity"
        )
    if quantity.is_zero:
        raise InvariantViolation("An item quantity must be greater than zero", field="quantity")


def _require_positive(amount: Money) -> Money:
    if not isinstance(amount, Money):
        raise ValidationError("amount must be Money", field="amount")
    if not amount.is_positive:
        raise InvariantViolation(
            "An expense must be greater than zero", amount=amount.minor_units
        )
    return amount


class Expense(AggregateRoot):
    """A single spend belonging to one Owner."""

    def __init__(
        self,
        expense_id: ExpenseId,
        *,
        owner_id: OwnerId,
        category_id: CategoryId,
        amount: Money,
        spent_on: SpendDate,
        note: str | None = None,
        payment_method: PaymentMethod = PaymentMethod.CASH,
        item_id: ItemId | None = None,
        quantity: Quantity | None = None,
        unit_id: UnitId | None = None,
    ) -> None:
        super().__init__(expense_id)
        if not isinstance(spent_on, SpendDate):
            raise ValidationError("spent_on must be a SpendDate", field="spent_on")
        _validate_item_line(item_id, quantity, unit_id)
        self._owner_id = owner_id
        self._category_id = category_id
        self._amount = _require_positive(amount)
        self._spent_on = spent_on
        self._note = clean_note(note)
        self._payment_method = PaymentMethod.parse(payment_method)
        self._item_id = item_id
        self._quantity = quantity
        self._unit_id = unit_id

    @classmethod
    def record(
        cls,
        *,
        owner_id: OwnerId,
        category_id: CategoryId,
        amount: Money,
        spent_on: SpendDate,
        note: str | None = None,
        payment_method: PaymentMethod | str | None = None,
        item_id: ItemId | None = None,
        quantity: Quantity | None = None,
        unit_id: UnitId | None = None,
        expense_id: ExpenseId | None = None,
    ) -> Expense:
        expense = cls(
            expense_id or ExpenseId.new(),
            owner_id=owner_id,
            category_id=category_id,
            amount=amount,
            spent_on=spent_on,
            note=note,
            payment_method=PaymentMethod.parse(payment_method),
            item_id=item_id,
            quantity=quantity,
            unit_id=unit_id,
        )
        expense.record_event(
            ExpenseRecorded(
                expense_id=expense.id,
                owner_id=owner_id,
                category_id=category_id,
                amount=expense.amount,
                spent_on=expense.spent_on.gregorian,
            )
        )
        return expense

    # -- state ----------------------------------------------------------
    @property
    def id(self) -> ExpenseId:
        return self._id  # type: ignore[return-value]

    @property
    def owner_id(self) -> OwnerId:
        return self._owner_id

    @property
    def category_id(self) -> CategoryId:
        return self._category_id

    @property
    def amount(self) -> Money:
        return self._amount

    @property
    def spent_on(self) -> SpendDate:
        return self._spent_on

    @property
    def note(self) -> str | None:
        return self._note

    @property
    def payment_method(self) -> PaymentMethod:
        return self._payment_method

    @property
    def item_id(self) -> ItemId | None:
        return self._item_id

    @property
    def quantity(self) -> Quantity | None:
        return self._quantity

    @property
    def unit_id(self) -> UnitId | None:
        return self._unit_id

    @property
    def has_item(self) -> bool:
        return self._item_id is not None

    def falls_in(self, period: Period) -> bool:
        return period.contains(self._spent_on.gregorian)

    def period(self, calendar: CalendarKind | str) -> Period:
        return self._spent_on.period(calendar)

    # -- behaviour ------------------------------------------------------
    def change_amount(self, amount: Money) -> None:
        if amount.currency != self._amount.currency:
            raise InvariantViolation(
                "An expense cannot change currency; delete it and record a new one",
                was=self._amount.currency,
                given=amount.currency,
            )
        self._amount = _require_positive(amount)

    def recategorise(self, category_id: CategoryId) -> None:
        self._category_id = category_id

    def move_to(self, spent_on: SpendDate) -> None:
        if not isinstance(spent_on, SpendDate):
            raise ValidationError("spent_on must be a SpendDate", field="spent_on")
        self._spent_on = spent_on

    def amend_note(self, note: str | None) -> None:
        self._note = clean_note(note)

    def change_payment_method(self, payment_method: PaymentMethod | str | None) -> None:
        self._payment_method = PaymentMethod.parse(payment_method)

    def set_item(self, item_id: ItemId, quantity: Quantity, unit_id: UnitId) -> None:
        """Attach (or replace) the item line: what was bought, how much, in what unit."""
        _validate_item_line(item_id, quantity, unit_id)
        self._item_id = item_id
        self._quantity = quantity
        self._unit_id = unit_id

    def clear_item(self) -> None:
        """Drop the item line, leaving a plain amount-only expense."""
        self._item_id = None
        self._quantity = None
        self._unit_id = None
