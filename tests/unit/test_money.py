from decimal import Decimal

import pytest

from kise.shared_kernel.domain.errors import ValidationError
from kise.shared_kernel.domain.money import CurrencyMismatch, Money, sum_money


def test_money_is_integer_minor_units():
    assert Money(125075).minor_units == 125075
    assert Money(125075).currency == "ETB"
    assert Money(125075).major_units == Decimal("1250.75")


def test_money_rejects_floats_and_bools():
    with pytest.raises(ValidationError):
        Money(10.5)  # type: ignore[arg-type]
    with pytest.raises(ValidationError):
        Money(True)  # type: ignore[arg-type]


def test_from_major_scales_and_rejects_extra_precision():
    assert Money.from_major("1250.75") == Money(125075)
    assert Money.from_major(1250) == Money(125000)
    with pytest.raises(ValidationError):
        Money.from_major("10.005")


def test_currency_is_normalised_and_validated():
    assert Money(100, "etb").currency == "ETB"
    with pytest.raises(ValidationError):
        Money(100, "BIRR")
    with pytest.raises(ValidationError):
        Money(100, "E1B")


def test_arithmetic_stays_exact():
    total = sum_money([Money.from_major("0.10")] * 10)
    assert total == Money.from_major("1.00")
    assert total.minor_units == 100
    assert Money(300) - Money(100) == Money(200)
    assert Money(150).times(3) == Money(450)


def test_mixing_currencies_is_a_domain_error():
    with pytest.raises(CurrencyMismatch):
        Money(100, "ETB") + Money(100, "USD")
    with pytest.raises(CurrencyMismatch):
        assert Money(100, "ETB") < Money(100, "USD")


def test_multiplying_by_a_float_is_rejected():
    with pytest.raises(ValidationError):
        Money(100).times(1.5)  # type: ignore[arg-type]


def test_comparison_and_predicates():
    assert Money(100) > Money(99)
    assert Money(0).is_zero
    assert not Money(0).is_positive
    assert Money(1).is_positive
    assert Money(-1).is_positive is False


def test_share_of_handles_zero_total():
    assert Money(2500).share_of(Money(10000)) == 0.25
    assert Money(0).share_of(Money(0)) == 0.0


def test_format():
    assert Money(125075).format() == "1,250.75 ETB"


def test_money_is_hashable_and_compared_by_value():
    assert Money(100) == Money(100)
    assert len({Money(100), Money(100), Money(200)}) == 2
