"""Typed identifiers.

Ids are UUIDs generated **in the domain**, never by the database, so an aggregate is complete and
valid the moment it is constructed. Each aggregate gets its own id type, which makes passing an
``OwnerId`` where a ``CategoryId`` belongs a type error rather than a silent bug.
"""

from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID, uuid4

from kise.shared_kernel.domain.errors import ValidationError


@dataclass(frozen=True, slots=True)
class EntityId:
    """A UUID wrapped in a per-aggregate type."""

    value: UUID

    def __post_init__(self) -> None:
        if not isinstance(self.value, UUID):
            raise ValidationError(f"{type(self).__name__} must wrap a UUID, got {self.value!r}")

    @classmethod
    def new(cls):  # noqa: ANN206 - returns cls
        return cls(uuid4())

    @classmethod
    def parse(cls, text: str):  # noqa: ANN206 - returns cls
        try:
            return cls(UUID(str(text)))
        except (ValueError, AttributeError, TypeError) as exc:
            raise ValidationError(f"Invalid {cls.__name__}: {text!r}") from exc

    def __str__(self) -> str:
        return str(self.value)


class OwnerId(EntityId):
    """Identifies an Owner (Identity context)."""


class CategoryId(EntityId):
    """Identifies a Category."""


class ExpenseId(EntityId):
    """Identifies a Dynamic Expense."""


class FixedExpenseId(EntityId):
    """Identifies a Fixed Monthly Expense."""


class SettlementId(EntityId):
    """Identifies a Settlement inside a Fixed Monthly Expense."""


class UnitId(EntityId):
    """Identifies a Unit of Measurement (kg, litre, piece, ...)."""


class ItemId(EntityId):
    """Identifies an Item — a thing bought, tracked across expenses."""
