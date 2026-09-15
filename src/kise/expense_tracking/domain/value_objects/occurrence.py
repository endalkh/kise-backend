"""Occurrence — a Fixed Monthly Expense projected into one Period.

An Occurrence is a **value object, computed on demand**, never a stored row. Nothing about a future
month is written down, so an unpaid ነሐሴ costs zero rows and a commitment that runs for years does
not grow a table. Only Settlements — the months actually paid — are persisted.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date

from kise.shared_kernel.domain.calendar.period import Period
from kise.shared_kernel.domain.identifiers import CategoryId, FixedExpenseId
from kise.shared_kernel.domain.money import Money


@dataclass(frozen=True, slots=True)
class Occurrence:
    """What one Fixed Monthly Expense owes in one Period, and whether it has been settled."""

    fixed_expense_id: FixedExpenseId
    category_id: CategoryId
    title: str
    period: Period
    """The Period in the commitment's own Anchor Calendar — the key a Settlement is filed under."""
    due_date: date
    amount: Money
    """The settled amount when settled, otherwise the commitment's current amount."""
    is_settled: bool = False
    settled_on: date | None = None

    @property
    def is_outstanding(self) -> bool:
        return not self.is_settled

    @property
    def committed(self) -> Money:
        """Counted toward the Period's total whether or not it has been settled."""
        return self.amount

    @property
    def settled(self) -> Money:
        return self.amount if self.is_settled else Money.zero(self.amount.currency)

    @property
    def outstanding(self) -> Money:
        return Money.zero(self.amount.currency) if self.is_settled else self.amount
