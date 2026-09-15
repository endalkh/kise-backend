"""Failures the Expense Tracking context can raise."""

from __future__ import annotations

from kise.shared_kernel.domain.calendar.period import Period
from kise.shared_kernel.domain.errors import Conflict, InvariantViolation, NotFound


class CategoryNotFound(NotFound):
    code = "category_not_found"


class ExpenseNotFound(NotFound):
    code = "expense_not_found"


class FixedExpenseNotFound(NotFound):
    code = "fixed_expense_not_found"


class ItemNotFound(NotFound):
    code = "item_not_found"


class UnitNotFound(NotFound):
    code = "unit_not_found"


class ItemNameTaken(Conflict):
    code = "item_name_taken"

    def __init__(self, name: str) -> None:
        super().__init__(f"An item named {name!r} already exists", name=name)


class UnitCodeTaken(Conflict):
    code = "unit_code_taken"

    def __init__(self, code: str) -> None:
        super().__init__(f"A unit with code {code!r} already exists", unit_code=code)


class ItemInUse(Conflict):
    """An item referenced by expenses is archived, never deleted, so history stays readable."""

    code = "item_in_use"

    def __init__(self, expense_count: int) -> None:
        super().__init__(
            "This item is used by recorded expenses, so it was archived instead of deleted",
            expense_count=expense_count,
        )


class SystemUnitProtected(Conflict):
    """A seeded system unit cannot be deleted; an expense recorded against it must not dangle."""

    code = "system_unit_protected"

    def __init__(self, code: str) -> None:
        super().__init__(f"The system unit {code!r} cannot be removed", unit_code=code)


class ItemArchived(InvariantViolation):
    code = "item_archived"


class CategoryNameTaken(Conflict):
    code = "category_name_taken"

    def __init__(self, name: str) -> None:
        super().__init__(f"A category named {name!r} already exists", name=name)


class CategoryInUse(Conflict):
    """A category with expenses attached is archived, never deleted, so history stays readable."""

    code = "category_in_use"

    def __init__(self, expense_count: int) -> None:
        super().__init__(
            "This category is used by recorded expenses, so it was archived instead of deleted",
            expense_count=expense_count,
        )


class CategoryArchived(InvariantViolation):
    code = "category_archived"


class NotOwned(InvariantViolation):
    """A record was reached for that belongs to a different Owner."""

    code = "not_owned"

    def __init__(self, what: str = "record") -> None:
        super().__init__(f"That {what} belongs to someone else")


class PeriodNotActive(InvariantViolation):
    code = "period_not_active"

    def __init__(self, period: Period) -> None:
        super().__init__(
            f"This commitment is not active in {period.label('en')}",
            period=str(period),
        )


class AlreadySettled(Conflict):
    code = "already_settled"

    def __init__(self, period: Period) -> None:
        super().__init__(
            f"{period.label('en')} is already settled; undo it first to change the amount",
            period=str(period),
        )


class NotSettled(Conflict):
    code = "not_settled"

    def __init__(self, period: Period) -> None:
        super().__init__(f"{period.label('en')} has not been settled", period=str(period))
