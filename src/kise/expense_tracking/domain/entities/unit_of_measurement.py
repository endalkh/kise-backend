"""The Unit of Measurement aggregate — kilogram, litre, piece, and whatever an admin adds.

Units are a *model*, not a hardcoded enum, precisely because the request was that the initial set
ship as data and an admin can extend it. So a Unit is a small aggregate with its own table, seeded
with a sensible default set on first run.

Two kinds exist, distinguished by ``is_system``:

* **system units** — the seeded set (kg, g, l, ml, pcs, ...). They are always present and cannot be
  deleted, so an expense recorded against "kg" never dangles.
* **custom units** — added by an admin for a need the defaults do not cover ("crate", "quintal").

A unit's ``code`` is its stable, lowercase identity ("kg"), unique across the system; ``name`` and
``name_am`` are how it reads in each language.
"""

from __future__ import annotations

from kise.expense_tracking.domain.value_objects.values import (
    clean_optional_text,
    clean_required_text,
)
from kise.shared_kernel.domain.entity import AggregateRoot
from kise.shared_kernel.domain.errors import ValidationError
from kise.shared_kernel.domain.identifiers import UnitId

MAX_UNIT_CODE_LENGTH = 16
MAX_UNIT_NAME_LENGTH = 40


def _clean_code(raw: str) -> str:
    """A unit code is a short, lowercase, whitespace-free token — its stable identity."""
    cleaned = clean_required_text(raw, field="code", max_length=MAX_UNIT_CODE_LENGTH)
    token = cleaned.lower().replace(" ", "")
    if not token:
        raise ValidationError("Unit code is required", field="code")
    return token


class UnitOfMeasurement(AggregateRoot):
    """A way of counting an item: kilograms, litres, pieces."""

    def __init__(
        self,
        unit_id: UnitId,
        *,
        code: str,
        name: str,
        name_am: str | None = None,
        is_system: bool = False,
    ) -> None:
        super().__init__(unit_id)
        self._code = _clean_code(code)
        self._name = clean_required_text(name, field="name", max_length=MAX_UNIT_NAME_LENGTH)
        self._name_am = clean_optional_text(
            name_am, field="name_am", max_length=MAX_UNIT_NAME_LENGTH
        )
        self._is_system = is_system

    @classmethod
    def create(
        cls,
        *,
        code: str,
        name: str,
        name_am: str | None = None,
        is_system: bool = False,
        unit_id: UnitId | None = None,
    ) -> UnitOfMeasurement:
        return cls(
            unit_id or UnitId.new(),
            code=code,
            name=name,
            name_am=name_am,
            is_system=is_system,
        )

    @property
    def id(self) -> UnitId:
        return self._id  # type: ignore[return-value]

    @property
    def code(self) -> str:
        return self._code

    @property
    def name(self) -> str:
        return self._name

    @property
    def name_am(self) -> str | None:
        return self._name_am

    @property
    def is_system(self) -> bool:
        return self._is_system

    def label(self, language: str = "am") -> str:
        if language == "am" and self._name_am:
            return self._name_am
        return self._name

    def rename(self, name: str, name_am: str | None = None) -> None:
        self._name = clean_required_text(name, field="name", max_length=MAX_UNIT_NAME_LENGTH)
        if name_am is not None:
            self._name_am = clean_optional_text(
                name_am, field="name_am", max_length=MAX_UNIT_NAME_LENGTH
            )


#: The units every install starts with: (code, english, amharic).
DEFAULT_UNITS: tuple[tuple[str, str, str], ...] = (
    ("kg", "Kilogram", "ኪሎግራም"),
    ("g", "Gram", "ግራም"),
    ("quintal", "Quintal", "ኩንታል"),
    ("l", "Litre", "ሊትር"),
    ("ml", "Millilitre", "ሚሊ ሊትር"),
    ("pcs", "Piece", "ቁራጭ"),
    ("dozen", "Dozen", "ደርዘን"),
    ("pack", "Pack", "ጥቅል"),
    ("bundle", "Bundle", "እስር"),
    ("bag", "Bag", "ከረጢት"),
)


def default_units() -> list[UnitOfMeasurement]:
    """Build the seeded set. Used once at startup by the composition root."""
    return [
        UnitOfMeasurement.create(code=code, name=name, name_am=name_am, is_system=True)
        for code, name, name_am in DEFAULT_UNITS
    ]
