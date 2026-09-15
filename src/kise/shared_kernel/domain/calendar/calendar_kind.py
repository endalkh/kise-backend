"""Which calendar a value is expressed in."""

from __future__ import annotations

from enum import StrEnum

from kise.shared_kernel.domain.errors import ValidationError


class CalendarKind(StrEnum):
    """The two calendars Kise speaks. Ethiopian has 13 months, Gregorian 12."""

    ETHIOPIAN = "ethiopian"
    GREGORIAN = "gregorian"

    @property
    def months_per_year(self) -> int:
        return 13 if self is CalendarKind.ETHIOPIAN else 12

    @property
    def other(self) -> CalendarKind:
        return (
            CalendarKind.GREGORIAN if self is CalendarKind.ETHIOPIAN else CalendarKind.ETHIOPIAN
        )

    @classmethod
    def parse(cls, value: str | CalendarKind) -> CalendarKind:
        if isinstance(value, CalendarKind):
            return value
        try:
            return cls(str(value).strip().lower())
        except ValueError as exc:
            raise ValidationError(
                f"Unknown calendar {value!r}; expected 'ethiopian' or 'gregorian'",
                field="calendar",
            ) from exc


class Language(StrEnum):
    """UI language, which decides whether month names render in Ethiopic or Latin script."""

    AMHARIC = "am"
    ENGLISH = "en"

    @classmethod
    def parse(cls, value: str | Language) -> Language:
        if isinstance(value, Language):
            return value
        try:
            return cls(str(value).strip().lower())
        except ValueError as exc:
            raise ValidationError(
                f"Unknown language {value!r}; expected 'am' or 'en'", field="language"
            ) from exc
