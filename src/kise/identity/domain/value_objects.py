"""Value objects of the Identity context — compared by value, immutable, self-validating."""

from __future__ import annotations

import re
from dataclasses import dataclass, replace

from kise.shared_kernel.domain.calendar.calendar_kind import CalendarKind, Language
from kise.shared_kernel.domain.errors import ValidationError
from kise.shared_kernel.domain.money import DEFAULT_CURRENCY

MAX_DISPLAY_NAME_LENGTH = 60
MAX_EMAIL_LENGTH = 254

# Deliberately permissive: the domain rejects what is obviously not an address and leaves
# deliverability to reality. Over-strict email regexes reject valid addresses.
_EMAIL_PATTERN = re.compile(r"^[^@\s]+@[^@\s.]+(\.[^@\s.]+)+$")


@dataclass(frozen=True, slots=True)
class EmailAddress:
    """An email address, normalised to lower case so it can serve as a unique key."""

    value: str

    def __post_init__(self) -> None:
        raw = self.value
        if not isinstance(raw, str):
            raise ValidationError("Email address must be text", field="email")
        cleaned = raw.strip().lower()
        if not cleaned:
            raise ValidationError("Email address is required", field="email")
        if len(cleaned) > MAX_EMAIL_LENGTH:
            raise ValidationError("Email address is too long", field="email")
        if not _EMAIL_PATTERN.match(cleaned):
            raise ValidationError(f"{raw!r} is not a valid email address", field="email")
        if cleaned != raw:
            object.__setattr__(self, "value", cleaned)

    def __str__(self) -> str:
        return self.value


@dataclass(frozen=True, slots=True)
class PasswordHash:
    """An already-hashed password.

    The domain never hashes and never sees a plaintext password — that is the ``PasswordHasher``
    port's job. This type exists so a raw password can never be stored by accident.
    """

    value: str

    def __post_init__(self) -> None:
        if not isinstance(self.value, str) or not self.value.strip():
            raise ValidationError("Password hash is required", field="password_hash")

    def __str__(self) -> str:  # pragma: no cover - avoid leaking hashes into logs
        return "<password hash>"

    __repr__ = __str__


@dataclass(frozen=True, slots=True)
class Preferences:
    """How the Owner wants Kise presented: which calendar, which language, which currency."""

    calendar: CalendarKind = CalendarKind.ETHIOPIAN
    language: Language = Language.AMHARIC
    currency: str = DEFAULT_CURRENCY

    def __post_init__(self) -> None:
        calendar = CalendarKind.parse(self.calendar)
        if calendar is not self.calendar:
            object.__setattr__(self, "calendar", calendar)
        language = Language.parse(self.language)
        if language is not self.language:
            object.__setattr__(self, "language", language)
        code = self.currency
        if not isinstance(code, str) or len(code) != 3 or not code.isalpha():
            raise ValidationError(
                f"Currency must be three letters, got {self.currency!r}", field="currency"
            )
        if not code.isupper():
            object.__setattr__(self, "currency", code.upper())

    def with_calendar(self, calendar: CalendarKind | str) -> Preferences:
        return replace(self, calendar=CalendarKind.parse(calendar))

    def with_language(self, language: Language | str) -> Preferences:
        return replace(self, language=Language.parse(language))

    def with_currency(self, currency: str) -> Preferences:
        return replace(self, currency=currency)


def clean_display_name(raw: str) -> str:
    if not isinstance(raw, str):
        raise ValidationError("Display name must be text", field="display_name")
    cleaned = " ".join(raw.split())
    if not cleaned:
        raise ValidationError("Display name is required", field="display_name")
    if len(cleaned) > MAX_DISPLAY_NAME_LENGTH:
        raise ValidationError(
            f"Display name must be at most {MAX_DISPLAY_NAME_LENGTH} characters",
            field="display_name",
        )
    return cleaned
