"""Small value objects shared by the Expense Tracking aggregates."""

from __future__ import annotations

import re
from dataclasses import dataclass
from enum import StrEnum

from kise.shared_kernel.domain.errors import ValidationError

MAX_CATEGORY_NAME_LENGTH = 60
MAX_TITLE_LENGTH = 80
MAX_NOTE_LENGTH = 500
MAX_ICON_LENGTH = 40

_HEX_COLOR = re.compile(r"^#[0-9a-fA-F]{6}$")


class PaymentMethod(StrEnum):
    """How an amount left the Owner's hands. Telebirr is listed because in Ethiopia it is not
    an edge case."""

    CASH = "cash"
    BANK = "bank"
    TELEBIRR = "telebirr"
    CARD = "card"
    OTHER = "other"

    @classmethod
    def parse(cls, value: str | PaymentMethod | None) -> PaymentMethod:
        if value is None:
            return cls.CASH
        if isinstance(value, PaymentMethod):
            return value
        try:
            return cls(str(value).strip().lower())
        except ValueError as exc:
            allowed = ", ".join(m.value for m in cls)
            raise ValidationError(
                f"Unknown payment method {value!r}; expected one of {allowed}",
                field="payment_method",
            ) from exc


@dataclass(frozen=True, slots=True)
class Color:
    """A ``#RRGGBB`` colour, used to make categories recognisable at a glance."""

    value: str = "#607D8B"

    def __post_init__(self) -> None:
        raw = self.value
        if not isinstance(raw, str) or not _HEX_COLOR.match(raw.strip()):
            raise ValidationError(
                f"Colour must look like #RRGGBB, got {self.value!r}", field="color"
            )
        normalised = raw.strip().upper()
        if normalised != raw:
            object.__setattr__(self, "value", normalised)

    def __str__(self) -> str:
        return self.value


def clean_required_text(raw: str, *, field: str, max_length: int) -> str:
    """Collapse whitespace and insist on something being left."""
    if not isinstance(raw, str):
        raise ValidationError(f"{field} must be text", field=field)
    cleaned = " ".join(raw.split())
    if not cleaned:
        raise ValidationError(f"{field} is required", field=field)
    if len(cleaned) > max_length:
        raise ValidationError(f"{field} must be at most {max_length} characters", field=field)
    return cleaned


def clean_optional_text(raw: str | None, *, field: str, max_length: int) -> str | None:
    """Normalise optional text; blank becomes ``None`` so "empty" has one representation."""
    if raw is None:
        return None
    if not isinstance(raw, str):
        raise ValidationError(f"{field} must be text", field=field)
    cleaned = raw.strip()
    if not cleaned:
        return None
    if len(cleaned) > max_length:
        raise ValidationError(f"{field} must be at most {max_length} characters", field=field)
    return cleaned


def clean_note(raw: str | None) -> str | None:
    return clean_optional_text(raw, field="note", max_length=MAX_NOTE_LENGTH)
