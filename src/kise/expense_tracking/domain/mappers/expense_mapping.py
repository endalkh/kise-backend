"""The Expense mapping contract."""

from __future__ import annotations

from typing import Any, Protocol, runtime_checkable

from kise.expense_tracking.domain.models import Expense

__all__ = ["ExpenseMapping"]


@runtime_checkable
class ExpenseMapping(Protocol):
    """Translates the Expense aggregate between its domain form and its stored form.

    The implementation must preserve both halves of ``SpendDate``: the canonical Gregorian day and
    the calendar the Owner entered it in.
    """

    @staticmethod
    def to_model(aggregate: Expense) -> Any: ...

    @staticmethod
    def to_domain(model: Any) -> Expense: ...

    @staticmethod
    def update_model(model: Any, aggregate: Expense) -> None: ...
