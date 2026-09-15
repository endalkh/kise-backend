"""Quantity — how much of an item an expense covers, e.g. 1.5 kg or 3 pieces.

Stored the same way Money is: as an **integer**, here a count of thousandths (milli-units), so
``1.5`` is ``1500`` and no arithmetic in the system can drift into ``1.4999999``. Three decimal
places is enough for kilograms and litres in a household context, and a unit like "piece" simply
uses whole numbers.

The unit itself is *not* part of this value object: a Quantity is a pure number. Which unit it is
counted in lives on the Expense (a ``UnitId``), because the same item can be bought in different
units on different days.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from kise.shared_kernel.domain.errors import ValidationError

THOUSANDTHS_PER_UNIT = 1000
MAX_QUANTITY_MILLI = 1_000_000_000  # a billion milli-units = a million units; a sane ceiling


@dataclass(frozen=True, slots=True, order=True)
class Quantity:
    """A non-negative amount of some unit, as integer thousandths."""

    milli: int

    def __post_init__(self) -> None:
        if isinstance(self.milli, bool) or not isinstance(self.milli, int):
            raise ValidationError(
                f"Quantity must be whole thousandths, got {self.milli!r}", field="quantity"
            )
        if self.milli < 0:
            raise ValidationError("Quantity cannot be negative", field="quantity")
        if self.milli > MAX_QUANTITY_MILLI:
            raise ValidationError("Quantity is implausibly large", field="quantity")

    @classmethod
    def of(cls, amount: Decimal | int | str | float) -> Quantity:
        """Build from a human amount: ``Quantity.of("1.5")`` -> 1500 milli."""
        try:
            value = Decimal(str(amount))
        except Exception as exc:  # noqa: BLE001 - Decimal raises several types
            raise ValidationError(f"Not a valid quantity: {amount!r}", field="quantity") from exc
        scaled = value * THOUSANDTHS_PER_UNIT
        if scaled != scaled.to_integral_value():
            raise ValidationError(
                f"{amount} has more than three decimal places", field="quantity"
            )
        return cls(int(scaled))

    @property
    def is_zero(self) -> bool:
        return self.milli == 0

    @property
    def value(self) -> Decimal:
        """The amount as a Decimal, e.g. ``Decimal('1.500')``."""
        return (Decimal(self.milli) / THOUSANDTHS_PER_UNIT).quantize(Decimal("0.001"))

    def add(self, other: Quantity) -> Quantity:
        return Quantity(self.milli + other.milli)

    def __add__(self, other: Quantity) -> Quantity:
        return self.add(other)

    def format(self) -> str:
        """A tidy string: whole numbers lose their decimals, ``1.500`` shows as ``1.5``."""
        text = format(self.value.normalize(), "f")
        return text

    def __str__(self) -> str:  # pragma: no cover - convenience
        return self.format()
