"""The Category mapping contract."""

from __future__ import annotations

from typing import Any, Protocol, runtime_checkable

from kise.expense_tracking.domain.models import Category

__all__ = ["CategoryMapping"]


@runtime_checkable
class CategoryMapping(Protocol):
    """Translates the Category aggregate between its domain form and its stored form."""

    @staticmethod
    def to_model(aggregate: Category) -> Any: ...

    @staticmethod
    def to_domain(model: Any) -> Category: ...

    @staticmethod
    def update_model(model: Any, aggregate: Category) -> None: ...
