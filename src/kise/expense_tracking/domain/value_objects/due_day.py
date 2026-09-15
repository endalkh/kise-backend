"""DueDay — the day of the month a Fixed Monthly Expense falls due.

A value object rather than an ``int`` because two rules travel with it, and they were being restated
every time the number was accepted:

* it runs 1..30, since Ethiopian months have 30 days and ጳጉሜን fewer still. "The last day" is
  expressed as 30;
* landing it in a real Period means **clamping** — day 30 becomes ጳጉሜን 5, or 28/29 February.

Keeping both here means an aggregate can accept a due day without knowing either rule.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date

from kise.shared_kernel.domain.calendar.period import Period
from kise.shared_kernel.domain.errors import ValidationError

#: Ethiopian months have 30 days, so a due day never exceeds 30. Gregorian 31 would be clamped
#: anyway, and allowing it would suggest a distinction that does not exist.
MAX_DUE_DAY = 30


@dataclass(frozen=True, slots=True)
class DueDay:
    """A day-of-month between 1 and 30."""

    value: int = 1

    def __post_init__(self) -> None:
        if isinstance(self.value, bool) or not isinstance(self.value, int):
            raise ValidationError("due_day must be a whole number", field="due_day")
        if not 1 <= self.value <= MAX_DUE_DAY:
            raise ValidationError(
                f"due_day must be between 1 and {MAX_DUE_DAY}, got {self.value}", field="due_day"
            )

    @classmethod
    def of(cls, value: int | DueDay) -> DueDay:
        return value if isinstance(value, DueDay) else cls(value)

    def on(self, period: Period) -> date:
        """The Gregorian date this due day falls on in ``period``, clamped to the month's length."""
        return period.day(self.value)

    def is_clamped_in(self, period: Period) -> bool:
        """Whether this due day had to be pulled back to fit — true for day 30 in ጳጉሜን."""
        return self.value > period.length_in_days

    def __int__(self) -> int:
        return self.value

    def __str__(self) -> str:  # pragma: no cover - convenience
        return str(self.value)
