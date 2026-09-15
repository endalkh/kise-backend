"""SpendDate — the day something was spent, in both calendars at once.

The Gregorian value is canonical and is what the database stores; the Ethiopian view is derived.
``entered_in`` remembers which calendar the Owner actually typed, so the app can echo a date back
the way it was entered even after they switch their preference.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date

from kise.shared_kernel.domain.calendar.calendar_kind import CalendarKind
from kise.shared_kernel.domain.calendar.ethiopian import (
    ETHIOPIAN_WEEKDAY_NAMES_AM,
    GREGORIAN_MONTH_NAMES_EN,
    EthiopianDate,
)
from kise.shared_kernel.domain.calendar.period import Period
from kise.shared_kernel.domain.errors import ValidationError


@dataclass(frozen=True, slots=True)
class SpendDate:
    """A calendar day, canonical in Gregorian, aware of how it was entered."""

    value: date
    entered_in: CalendarKind = CalendarKind.GREGORIAN

    def __post_init__(self) -> None:
        if not isinstance(self.value, date):
            raise ValidationError(f"SpendDate needs a date, got {self.value!r}", field="value")
        kind = CalendarKind.parse(self.entered_in)
        if kind is not self.entered_in:
            object.__setattr__(self, "entered_in", kind)

    # -- construction ---------------------------------------------------
    @classmethod
    def from_gregorian(cls, value: date) -> SpendDate:
        return cls(value, CalendarKind.GREGORIAN)

    @classmethod
    def from_ethiopian(cls, year: int, month: int, day: int) -> SpendDate:
        return cls(EthiopianDate(year, month, day).to_gregorian(), CalendarKind.ETHIOPIAN)

    @classmethod
    def parse(cls, text: str, calendar: CalendarKind | str) -> SpendDate:
        """Parse ``YYYY-MM-DD`` written in the given calendar."""
        kind = CalendarKind.parse(calendar)
        if kind is CalendarKind.ETHIOPIAN:
            return cls(EthiopianDate.parse(text).to_gregorian(), kind)
        try:
            return cls(date.fromisoformat(text.strip()), kind)
        except (ValueError, AttributeError) as exc:
            raise ValidationError(
                f"Expected a Gregorian date as YYYY-MM-DD, got {text!r}", field="value"
            ) from exc

    # -- views ----------------------------------------------------------
    @property
    def ethiopian(self) -> EthiopianDate:
        return EthiopianDate.from_gregorian(self.value)

    @property
    def gregorian(self) -> date:
        return self.value

    def period(self, calendar: CalendarKind | str) -> Period:
        return Period.from_date(self.value, calendar)

    @property
    def own_period(self) -> Period:
        """The Period of the calendar this date was entered in."""
        return self.period(self.entered_in)

    # -- comparison -----------------------------------------------------
    def __lt__(self, other: SpendDate) -> bool:
        return self.value < other.value

    def __le__(self, other: SpendDate) -> bool:
        return self.value <= other.value

    def __gt__(self, other: SpendDate) -> bool:
        return self.value > other.value

    def __ge__(self, other: SpendDate) -> bool:
        return self.value >= other.value

    # -- rendering ------------------------------------------------------
    def label(self, calendar: CalendarKind | str, language: str = "am") -> str:
        kind = CalendarKind.parse(calendar)
        if kind is CalendarKind.ETHIOPIAN:
            return self.ethiopian.format(language)
        name = GREGORIAN_MONTH_NAMES_EN[self.value.month - 1]
        return f"{name} {self.value.day}, {self.value.year}"

    def describe(self) -> dict[str, object]:
        """Both calendars, as the API returns every date."""
        et = self.ethiopian
        return {
            "gregorian": self.value.isoformat(),
            "gregorian_month_name": GREGORIAN_MONTH_NAMES_EN[self.value.month - 1],
            "ethiopian": et.iso,
            "ethiopian_year": et.year,
            "ethiopian_month": et.month,
            "ethiopian_day": et.day,
            "ethiopian_month_name_am": et.month_name_am,
            "ethiopian_month_name_en": et.month_name_en,
            "weekday_am": ETHIOPIAN_WEEKDAY_NAMES_AM[self.value.weekday()],
            "entered_in": self.entered_in.value,
        }

    def __str__(self) -> str:  # pragma: no cover - convenience
        return self.value.isoformat()
