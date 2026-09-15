"""Value-object <-> column conversions shared by every mapper.

``Money`` and ``Period`` are single domain concepts stored across two or three columns. Doing that
translation in one place keeps every mapper honest about it, and means a change to how money is
stored touches exactly one file.

The mapping *contract* lives in the domain, at ``shared_kernel/domain/mapper.py``; it is re-exported
here so an infrastructure mapper can import both from one place.
"""

from __future__ import annotations

from kise.shared_kernel.domain.calendar.calendar_kind import CalendarKind
from kise.shared_kernel.domain.calendar.period import Period
from kise.shared_kernel.domain.mapper import AggregateT, Mapper, ModelT
from kise.shared_kernel.domain.money import Money

__all__ = [
    "AggregateT",
    "Mapper",
    "ModelT",
    "money_from_columns",
    "money_to_columns",
    "period_from_columns",
    "period_to_columns",
]


def money_to_columns(amount: Money) -> tuple[int, str]:
    return amount.minor_units, amount.currency


def money_from_columns(minor_units: int, currency: str) -> Money:
    return Money(minor_units, currency)


def period_to_columns(period: Period) -> tuple[str, int, int]:
    return period.calendar.value, period.year, period.month


def period_from_columns(calendar: str, year: int, month: int) -> Period:
    return Period(CalendarKind.parse(calendar), year, month)
