"""PeriodRange — a run of months in one calendar, open-ended or closed.

This exists because the same three rules were being restated in three places in ``FixedExpense``
(the constructor, ``end_after`` and ``start_from``):

* the start and end Periods must be in the same Anchor Calendar;
* the end may not come before the start;
* no end at all means "still running".

Holding them here makes them testable on their own and makes "is this month inside the run?" a
single call instead of a pair of comparisons the caller has to remember to write.
"""

from __future__ import annotations

from dataclasses import dataclass

from kise.shared_kernel.domain.calendar.calendar_kind import CalendarKind
from kise.shared_kernel.domain.calendar.period import Period
from kise.shared_kernel.domain.errors import InvariantViolation, ValidationError


@dataclass(frozen=True, slots=True)
class PeriodRange:
    """An inclusive span of Periods; ``end`` of ``None`` means open-ended."""

    start: Period
    end: Period | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.start, Period):
            raise ValidationError("A PeriodRange needs a start Period", field="start_period")
        if self.end is None:
            return
        if not isinstance(self.end, Period):
            raise ValidationError("end must be a Period or None", field="end_period")
        if self.end.calendar is not self.start.calendar:
            raise InvariantViolation(
                "The start and end Periods must be in the same Anchor Calendar",
                start=self.start.calendar.value,
                end=self.end.calendar.value,
            )
        if self.end < self.start:
            raise InvariantViolation(
                "A commitment cannot end before it starts",
                start=str(self.start),
                end=str(self.end),
            )

    # -- state ----------------------------------------------------------
    @property
    def calendar(self) -> CalendarKind:
        """The Anchor Calendar: the one the whole range is expressed in."""
        return self.start.calendar

    @property
    def is_open_ended(self) -> bool:
        return self.end is None

    @property
    def length_in_months(self) -> int | None:
        """How many Periods the range covers, or ``None`` while it is still running."""
        if self.end is None:
            return None
        return self.end.index - self.start.index + 1

    # -- membership -----------------------------------------------------
    def contains(self, period: Period) -> bool:
        """Is ``period`` inside the range? Converted to the Anchor Calendar first if need be."""
        anchor = period.as_calendar(self.calendar)
        if anchor < self.start:
            return False
        return self.end is None or anchor <= self.end

    def periods(self) -> list[Period]:
        """Every Period in a closed range. Refused while open-ended, which would be infinite."""
        if self.end is None:
            raise InvariantViolation(
                "An open-ended range has no last Period; ask for a specific span instead"
            )
        return self.start.iterate_to(self.end)

    # -- change ---------------------------------------------------------
    def with_end(self, end: Period | None) -> PeriodRange:
        """A copy ending at ``end``; ``None`` reopens it. Validation happens in the constructor."""
        if end is not None and end.calendar is not self.calendar:
            raise InvariantViolation(
                "The end Period must be in the range's Anchor Calendar",
                anchor=self.calendar.value,
                given=end.calendar.value,
            )
        return PeriodRange(self.start, end)

    def with_start(self, start: Period) -> PeriodRange:
        if start.calendar is not self.calendar:
            raise InvariantViolation(
                "The start Period must stay in the range's Anchor Calendar",
                anchor=self.calendar.value,
                given=start.calendar.value,
            )
        return PeriodRange(start, self.end)

    def __str__(self) -> str:  # pragma: no cover - convenience
        return f"{self.start} .. {self.end or 'open'}"
