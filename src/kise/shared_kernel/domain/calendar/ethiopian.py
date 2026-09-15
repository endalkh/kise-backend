"""Ethiopian (Ge'ez) <-> Gregorian calendar conversion.

The Ethiopian calendar has 13 months: 12 months of 30 days plus Pagumen,
a short 13th month of 5 days (6 days in a leap year). Ethiopian leap years
are the years where ``year % 4 == 3``.

Conversion is done through the Julian Day Number (JDN) so it stays exact for
any date, including across Gregorian leap years and century boundaries.

Canonical storage rule for Kise: the database always stores Gregorian dates.
The Ethiopian representation is computed on the way in and out.
"""

from __future__ import annotations

from calendar import monthrange
from dataclasses import dataclass
from datetime import date

# JDN of Ethiopian 1-1-1 (Amete Mihret era) minus the algorithm's offsets.
_JD_EPOCH_OFFSET_AMETE_MIHRET = 1_723_856
# JDN of proleptic Gregorian 0001-01-01 is 1721426; date.toordinal() of that day is 1.
_GREGORIAN_ORDINAL_TO_JDN = 1_721_425

MONTHS_PER_YEAR = 13

#: Amharic month names, index 0 == Meskerem (month 1).
ETHIOPIAN_MONTH_NAMES_AM: tuple[str, ...] = (
    "መስከረም",
    "ጥቅምት",
    "ኅዳር",
    "ታኅሣሥ",
    "ጥር",
    "የካቲት",
    "መጋቢት",
    "ሚያዝያ",
    "ግንቦት",
    "ሰኔ",
    "ሐምሌ",
    "ነሐሴ",
    "ጳጉሜን",
)

#: Latin transliteration of the Ethiopian month names.
ETHIOPIAN_MONTH_NAMES_EN: tuple[str, ...] = (
    "Meskerem",
    "Tikimt",
    "Hidar",
    "Tahsas",
    "Tir",
    "Yekatit",
    "Megabit",
    "Miyazia",
    "Ginbot",
    "Sene",
    "Hamle",
    "Nehase",
    "Pagumen",
)

#: Amharic weekday names, index 0 == Monday (to match ``date.weekday()``).
ETHIOPIAN_WEEKDAY_NAMES_AM: tuple[str, ...] = (
    "ሰኞ",
    "ማክሰኞ",
    "ረቡዕ",
    "ሐሙስ",
    "ዓርብ",
    "ቅዳሜ",
    "እሁድ",
)

GREGORIAN_MONTH_NAMES_EN: tuple[str, ...] = (
    "January",
    "February",
    "March",
    "April",
    "May",
    "June",
    "July",
    "August",
    "September",
    "October",
    "November",
    "December",
)


class EthiopianDateError(ValueError):
    """Raised when an Ethiopian date does not exist."""


def is_ethiopian_leap_year(year: int) -> bool:
    """Ethiopian leap years are those where ``year % 4 == 3`` (Pagumen has 6 days)."""
    return year % 4 == 3


def ethiopian_month_length(year: int, month: int) -> int:
    _validate_month(month)
    if month == 13:
        return 6 if is_ethiopian_leap_year(year) else 5
    return 30


def _validate_month(month: int) -> None:
    if not 1 <= month <= MONTHS_PER_YEAR:
        raise EthiopianDateError(f"Ethiopian month must be between 1 and 13, got {month}")


def validate_ethiopian_date(year: int, month: int, day: int) -> None:
    if year < 1:
        raise EthiopianDateError(f"Ethiopian year must be >= 1, got {year}")
    _validate_month(month)
    length = ethiopian_month_length(year, month)
    if not 1 <= day <= length:
        name = ETHIOPIAN_MONTH_NAMES_EN[month - 1]
        raise EthiopianDateError(f"{name} {year} has {length} days, got day {day}")


def ethiopian_to_gregorian(year: int, month: int, day: int) -> date:
    """Convert an Ethiopian date to the equivalent Gregorian ``date``."""
    validate_ethiopian_date(year, month, day)
    jdn = (
        (_JD_EPOCH_OFFSET_AMETE_MIHRET + 365)
        + 365 * (year - 1)
        + year // 4
        + 30 * month
        + day
        - 31
    )
    return date.fromordinal(jdn - _GREGORIAN_ORDINAL_TO_JDN)


def gregorian_to_ethiopian(value: date) -> tuple[int, int, int]:
    """Convert a Gregorian ``date`` to an ``(year, month, day)`` Ethiopian tuple."""
    jdn = value.toordinal() + _GREGORIAN_ORDINAL_TO_JDN
    days_since_epoch = jdn - _JD_EPOCH_OFFSET_AMETE_MIHRET
    r = days_since_epoch % 1461
    n = (r % 365) + 365 * (r // 1460)
    year = 4 * (days_since_epoch // 1461) + (r // 365) - (r // 1460)
    month = n // 30 + 1
    day = n % 30 + 1
    return year, month, day


@dataclass(frozen=True, slots=True)
class EthiopianDate:
    """An Ethiopian calendar date with helpers to move to/from Gregorian."""

    year: int
    month: int
    day: int

    def __post_init__(self) -> None:
        validate_ethiopian_date(self.year, self.month, self.day)

    # -- construction ---------------------------------------------------
    @classmethod
    def from_gregorian(cls, value: date) -> EthiopianDate:
        return cls(*gregorian_to_ethiopian(value))

    @classmethod
    def today(cls) -> EthiopianDate:
        return cls.from_gregorian(date.today())

    @classmethod
    def parse(cls, text: str) -> EthiopianDate:
        """Parse ``YYYY-MM-DD`` in the Ethiopian calendar."""
        parts = text.strip().split("-")
        if len(parts) != 3:
            raise EthiopianDateError(f"Expected an Ethiopian date as YYYY-MM-DD, got {text!r}")
        try:
            year, month, day = (int(p) for p in parts)
        except ValueError as exc:  # noqa: TRY003
            raise EthiopianDateError(f"Invalid Ethiopian date {text!r}") from exc
        return cls(year, month, day)

    # -- conversion -----------------------------------------------------
    def to_gregorian(self) -> date:
        return ethiopian_to_gregorian(self.year, self.month, self.day)

    # -- formatting -----------------------------------------------------
    @property
    def month_name_am(self) -> str:
        return ETHIOPIAN_MONTH_NAMES_AM[self.month - 1]

    @property
    def month_name_en(self) -> str:
        return ETHIOPIAN_MONTH_NAMES_EN[self.month - 1]

    @property
    def iso(self) -> str:
        return f"{self.year:04d}-{self.month:02d}-{self.day:02d}"

    def format(self, locale: str = "am") -> str:
        name = self.month_name_am if locale == "am" else self.month_name_en
        return f"{name} {self.day}, {self.year}"

    def __str__(self) -> str:  # pragma: no cover - convenience
        return self.iso

    # -- arithmetic -----------------------------------------------------
    def add_days(self, days: int) -> EthiopianDate:
        return EthiopianDate.from_gregorian(
            date.fromordinal(self.to_gregorian().toordinal() + days)
        )

    def add_months(self, months: int) -> EthiopianDate:
        total = (self.year * MONTHS_PER_YEAR) + (self.month - 1) + months
        year, month_index = divmod(total, MONTHS_PER_YEAR)
        month = month_index + 1
        day = min(self.day, ethiopian_month_length(year, month))
        return EthiopianDate(year, month, day)


def ethiopian_month_bounds(year: int, month: int) -> tuple[date, date]:
    """Gregorian ``(first_day, last_day)`` of an Ethiopian month, inclusive."""
    _validate_month(month)
    first = ethiopian_to_gregorian(year, month, 1)
    last = ethiopian_to_gregorian(year, month, ethiopian_month_length(year, month))
    return first, last


def gregorian_month_bounds(year: int, month: int) -> tuple[date, date]:
    """Gregorian ``(first_day, last_day)`` of a Gregorian month, inclusive."""
    if not 1 <= month <= 12:
        raise ValueError(f"Gregorian month must be between 1 and 12, got {month}")
    return date(year, month, 1), date(year, month, monthrange(year, month)[1])


def month_index(year: int, month: int, months_per_year: int) -> int:
    """Absolute month number, used to compare/iterate months of either calendar."""
    return year * months_per_year + (month - 1)


def describe(value: date) -> dict[str, object]:
    """Both calendar representations of one Gregorian date, ready for JSON."""
    et = EthiopianDate.from_gregorian(value)
    return {
        "gregorian": value.isoformat(),
        "gregorian_month_name": GREGORIAN_MONTH_NAMES_EN[value.month - 1],
        "ethiopian": et.iso,
        "ethiopian_year": et.year,
        "ethiopian_month": et.month,
        "ethiopian_day": et.day,
        "ethiopian_month_name_am": et.month_name_am,
        "ethiopian_month_name_en": et.month_name_en,
        "weekday_am": ETHIOPIAN_WEEKDAY_NAMES_AM[value.weekday()],
    }
