"""Period — one month in a named calendar.

A Period is the unit of everything monthly in Kise: a Fixed Monthly Expense is active over a range
of Periods, an Occurrence belongs to exactly one, and a summary reports one.

The trick that keeps the two calendars from tangling is ``index``: a Period collapses to a single
integer inside its own calendar, so "is this commitment active in this month?" is an integer
comparison. Comparing *across* calendars is only ever done by overlapping the Gregorian spans, and
that happens in exactly one method — ``overlaps``.
"""

from __future__ import annotations

from calendar import monthrange
from dataclasses import dataclass
from datetime import date

from kise.shared_kernel.domain.calendar.calendar_kind import CalendarKind
from kise.shared_kernel.domain.calendar.ethiopian import (
    ETHIOPIAN_MONTH_NAMES_AM,
    ETHIOPIAN_MONTH_NAMES_EN,
    GREGORIAN_MONTH_NAMES_EN,
    EthiopianDate,
    ethiopian_month_bounds,
    ethiopian_month_length,
    ethiopian_to_gregorian,
    gregorian_month_bounds,
    gregorian_to_ethiopian,
)
from kise.shared_kernel.domain.errors import DomainError, ValidationError

#: Amharic renderings of the Gregorian month names, for the counterpart label.
GREGORIAN_MONTH_NAMES_AM: tuple[str, ...] = (
    "ጃንዩወሪ",
    "ፌብሩወሪ",
    "ማርች",
    "ኤፕሪል",
    "ሜይ",
    "ጁን",
    "ጁላይ",
    "ኦገስት",
    "ሴፕቴምበር",
    "ኦክቶበር",
    "ኖቬምበር",
    "ዲሴምበር",
)


class CalendarMismatch(DomainError):
    """Two Periods in different calendars were compared as if they were the same kind."""

    code = "calendar_mismatch"


@dataclass(frozen=True, slots=True)
class Period:
    """A (calendar, year, month) triple, e.g. ``(ethiopian, 2018, 11)`` = ሐምሌ 2018."""

    calendar: CalendarKind
    year: int
    month: int

    def __post_init__(self) -> None:
        calendar = CalendarKind.parse(self.calendar)
        if calendar is not self.calendar:
            object.__setattr__(self, "calendar", calendar)
        if not isinstance(self.year, int) or self.year < 1:
            raise ValidationError(f"Period year must be a positive integer, got {self.year!r}")
        if not isinstance(self.month, int) or not 1 <= self.month <= calendar.months_per_year:
            raise ValidationError(
                f"{calendar.value} months run 1..{calendar.months_per_year}, got {self.month!r}",
                field="month",
            )

    # -- construction ---------------------------------------------------
    @classmethod
    def of(cls, calendar: CalendarKind | str, year: int, month: int) -> Period:
        return cls(CalendarKind.parse(calendar), year, month)

    @classmethod
    def from_date(cls, value: date, calendar: CalendarKind | str) -> Period:
        """The Period of either calendar that contains a Gregorian date."""
        kind = CalendarKind.parse(calendar)
        if kind is CalendarKind.ETHIOPIAN:
            year, month, _ = gregorian_to_ethiopian(value)
            return cls(kind, year, month)
        return cls(kind, value.year, value.month)

    @classmethod
    def from_index(cls, calendar: CalendarKind | str, index: int) -> Period:
        kind = CalendarKind.parse(calendar)
        year, month_offset = divmod(index, kind.months_per_year)
        return cls(kind, year, month_offset + 1)

    # -- ordering inside one calendar -----------------------------------
    @property
    def index(self) -> int:
        """Absolute month number: ``year * months_per_year + (month - 1)``."""
        return self.year * self.calendar.months_per_year + (self.month - 1)

    def _assert_same_calendar(self, other: Period) -> None:
        if self.calendar is not other.calendar:
            raise CalendarMismatch(
                f"Cannot order a {self.calendar.value} Period against a "
                f"{other.calendar.value} one; use overlaps() instead",
                left=self.calendar.value,
                right=other.calendar.value,
            )

    def __lt__(self, other: Period) -> bool:
        self._assert_same_calendar(other)
        return self.index < other.index

    def __le__(self, other: Period) -> bool:
        self._assert_same_calendar(other)
        return self.index <= other.index

    def __gt__(self, other: Period) -> bool:
        self._assert_same_calendar(other)
        return self.index > other.index

    def __ge__(self, other: Period) -> bool:
        self._assert_same_calendar(other)
        return self.index >= other.index

    def shift(self, months: int) -> Period:
        return Period.from_index(self.calendar, self.index + months)

    @property
    def next(self) -> Period:
        return self.shift(1)

    @property
    def previous(self) -> Period:
        return self.shift(-1)

    def months_until(self, other: Period) -> int:
        self._assert_same_calendar(other)
        return other.index - self.index

    def iterate_to(self, last: Period) -> list[Period]:
        """Every Period from this one up to and including ``last``."""
        self._assert_same_calendar(last)
        return [Period.from_index(self.calendar, i) for i in range(self.index, last.index + 1)]

    # -- days -----------------------------------------------------------
    @property
    def length_in_days(self) -> int:
        if self.calendar is CalendarKind.ETHIOPIAN:
            return ethiopian_month_length(self.year, self.month)
        return monthrange(self.year, self.month)[1]

    def day(self, day_of_month: int) -> date:
        """Gregorian date of a day in this Period, clamped to the Period's length.

        Clamping is what makes a "due on the 30th" commitment behave in ጳጉሜን (5 days) and in
        February (28 or 29).
        """
        if day_of_month < 1:
            raise ValidationError(f"Day of month must be >= 1, got {day_of_month}")
        clamped = min(day_of_month, self.length_in_days)
        if self.calendar is CalendarKind.ETHIOPIAN:
            return ethiopian_to_gregorian(self.year, self.month, clamped)
        return date(self.year, self.month, clamped)

    @property
    def gregorian_span(self) -> tuple[date, date]:
        """Inclusive ``(first_day, last_day)`` of this Period as Gregorian dates."""
        if self.calendar is CalendarKind.ETHIOPIAN:
            return ethiopian_month_bounds(self.year, self.month)
        return gregorian_month_bounds(self.year, self.month)

    def contains(self, value: date) -> bool:
        first, last = self.gregorian_span
        return first <= value <= last

    def overlaps(self, other: Period) -> bool:
        """Do the two Periods share at least one day? The only cross-calendar comparison."""
        a_first, a_last = self.gregorian_span
        b_first, b_last = other.gregorian_span
        return a_first <= b_last and b_first <= a_last

    def as_calendar(self, calendar: CalendarKind | str) -> Period:
        """This stretch of time named in another calendar.

        Ethiopian and Gregorian months are both roughly 30 days but offset by about 10, so a Period
        of one calendar always straddles exactly two of the other. The counterpart is the one it
        shares the **most days** with, which is deterministic and matches what a person means when
        they say "ሐምሌ is basically July". Ties, which the offsets make impossible in practice, go to
        the earlier Period.
        """
        kind = CalendarKind.parse(calendar)
        if kind is self.calendar:
            return self
        first, last = self.gregorian_span
        candidates = {Period.from_date(first, kind), Period.from_date(last, kind)}
        return max(candidates, key=lambda other: (other.overlap_days(self), -other.index))

    def overlap_days(self, other: Period) -> int:
        """How many days the two Periods share; 0 when they are disjoint."""
        a_first, a_last = self.gregorian_span
        b_first, b_last = other.gregorian_span
        first = max(a_first, b_first)
        last = min(a_last, b_last)
        return max(0, (last - first).days + 1)

    # -- labels ---------------------------------------------------------
    @property
    def month_name_am(self) -> str:
        if self.calendar is CalendarKind.ETHIOPIAN:
            return ETHIOPIAN_MONTH_NAMES_AM[self.month - 1]
        return GREGORIAN_MONTH_NAMES_AM[self.month - 1]

    @property
    def month_name_en(self) -> str:
        if self.calendar is CalendarKind.ETHIOPIAN:
            return ETHIOPIAN_MONTH_NAMES_EN[self.month - 1]
        return GREGORIAN_MONTH_NAMES_EN[self.month - 1]

    def label(self, language: str = "am") -> str:
        """This Period in its own calendar, e.g. ``ሐምሌ 2018`` or ``July 2026``."""
        name = self.month_name_am if language == "am" else self.month_name_en
        return f"{name} {self.year}"

    def counterpart_label(self, language: str = "en") -> str:
        """The same stretch of time named in the *other* calendar.

        An Ethiopian Period straddles two Gregorian months, so this reads ``Jul - Aug 2026``.
        """
        first, last = self.gregorian_span
        other = self.calendar.other
        start = Period.from_date(first, other)
        end = Period.from_date(last, other)
        if start == end:
            return start.label(language)
        if start.year == end.year:
            start_name = start.month_name_am if language == "am" else start.month_name_en
            end_name = end.month_name_am if language == "am" else end.month_name_en
            return f"{start_name} - {end_name} {end.year}"
        return f"{start.label(language)} - {end.label(language)}"

    def labels(self) -> dict[str, str]:
        """Every rendering the API hands to the client."""
        first, last = self.gregorian_span
        return {
            "calendar": self.calendar.value,
            "label_am": self.label("am"),
            "label_en": self.label("en"),
            "counterpart_label_am": self.counterpart_label("am"),
            "counterpart_label_en": self.counterpart_label("en"),
            "first_day": first.isoformat(),
            "last_day": last.isoformat(),
        }

    def __str__(self) -> str:  # pragma: no cover - convenience
        return f"{self.calendar.value} {self.year}-{self.month:02d}"


def ethiopian_period(year: int, month: int) -> Period:
    return Period(CalendarKind.ETHIOPIAN, year, month)


def gregorian_period(year: int, month: int) -> Period:
    return Period(CalendarKind.GREGORIAN, year, month)


def period_of_ethiopian_date(value: EthiopianDate) -> Period:
    return Period(CalendarKind.ETHIOPIAN, value.year, value.month)
