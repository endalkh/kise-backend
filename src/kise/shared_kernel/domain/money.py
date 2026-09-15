"""Money as a value object.

Stored as an integer count of minor units (santim for ETB, cents elsewhere) so no arithmetic in the
system can ever hit floating-point drift. Currency is part of the value: adding ETB to USD is a
domain error, not a silent conversion.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from kise.shared_kernel.domain.errors import DomainError, ValidationError

MINOR_UNITS_PER_MAJOR = 100
DEFAULT_CURRENCY = "ETB"


class CurrencyMismatch(DomainError):
    """Two Money values of different currencies were combined."""

    code = "currency_mismatch"


@dataclass(frozen=True, slots=True, order=False)
class Money:
    """An amount of money: integer minor units plus an ISO-4217-style currency code."""

    minor_units: int
    currency: str = DEFAULT_CURRENCY

    def __post_init__(self) -> None:
        if isinstance(self.minor_units, bool) or not isinstance(self.minor_units, int):
            raise ValidationError(
                f"Money must be whole minor units, got {self.minor_units!r}",
                field="minor_units",
            )
        code = self.currency
        if not isinstance(code, str) or len(code) != 3 or not code.isalpha():
            raise ValidationError(
                f"Currency must be three letters, got {self.currency!r}", field="currency"
            )
        if not code.isupper():
            object.__setattr__(self, "currency", code.upper())

    # -- construction ---------------------------------------------------
    @classmethod
    def zero(cls, currency: str = DEFAULT_CURRENCY) -> Money:
        return cls(0, currency)

    @classmethod
    def from_major(cls, amount: Decimal | int | str, currency: str = DEFAULT_CURRENCY) -> Money:
        """Build from a major-unit amount, e.g. ``"1250.75"`` birr -> 125075 santim."""
        try:
            value = Decimal(str(amount))
        except Exception as exc:  # noqa: BLE001 - Decimal raises several types
            raise ValidationError(f"Not a valid amount: {amount!r}", field="amount") from exc
        scaled = value * MINOR_UNITS_PER_MAJOR
        if scaled != scaled.to_integral_value():
            raise ValidationError(
                f"{amount} has more precision than {currency} allows", field="amount"
            )
        return cls(int(scaled), currency)

    # -- arithmetic -----------------------------------------------------
    def _assert_same_currency(self, other: Money) -> None:
        if self.currency != other.currency:
            raise CurrencyMismatch(
                f"Cannot combine {self.currency} with {other.currency}",
                left=self.currency,
                right=other.currency,
            )

    def add(self, other: Money) -> Money:
        self._assert_same_currency(other)
        return Money(self.minor_units + other.minor_units, self.currency)

    def subtract(self, other: Money) -> Money:
        self._assert_same_currency(other)
        return Money(self.minor_units - other.minor_units, self.currency)

    def times(self, factor: int) -> Money:
        if isinstance(factor, bool) or not isinstance(factor, int):
            raise ValidationError("Money can only be multiplied by a whole number", field="factor")
        return Money(self.minor_units * factor, self.currency)

    def __add__(self, other: Money) -> Money:
        return self.add(other)

    def __sub__(self, other: Money) -> Money:
        return self.subtract(other)

    def __neg__(self) -> Money:
        return Money(-self.minor_units, self.currency)

    # -- comparison -----------------------------------------------------
    def __lt__(self, other: Money) -> bool:
        self._assert_same_currency(other)
        return self.minor_units < other.minor_units

    def __le__(self, other: Money) -> bool:
        self._assert_same_currency(other)
        return self.minor_units <= other.minor_units

    def __gt__(self, other: Money) -> bool:
        self._assert_same_currency(other)
        return self.minor_units > other.minor_units

    def __ge__(self, other: Money) -> bool:
        self._assert_same_currency(other)
        return self.minor_units >= other.minor_units

    # -- inspection -----------------------------------------------------
    @property
    def is_positive(self) -> bool:
        return self.minor_units > 0

    @property
    def is_zero(self) -> bool:
        return self.minor_units == 0

    @property
    def major_units(self) -> Decimal:
        return (Decimal(self.minor_units) / MINOR_UNITS_PER_MAJOR).quantize(Decimal("0.01"))

    def share_of(self, total: Money) -> float:
        """This amount as a fraction of ``total``; 0.0 when the total is zero."""
        self._assert_same_currency(total)
        if total.minor_units == 0:
            return 0.0
        return self.minor_units / total.minor_units

    def format(self) -> str:
        return f"{self.major_units:,.2f} {self.currency}"

    def __str__(self) -> str:  # pragma: no cover - convenience
        return self.format()


def sum_money(amounts: list[Money], currency: str = DEFAULT_CURRENCY) -> Money:
    """Total a list of Money, returning zero in ``currency`` when the list is empty."""
    total = Money.zero(currency)
    for amount in amounts:
        total = total.add(amount)
    return total
