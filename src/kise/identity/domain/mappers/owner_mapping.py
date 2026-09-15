"""The Owner mapping contract."""

from __future__ import annotations

from typing import Any, Protocol, runtime_checkable

from kise.identity.domain.models import Owner

__all__ = ["OwnerMapping"]


@runtime_checkable
class OwnerMapping(Protocol):
    """Translates the Owner aggregate between its domain form and its stored form."""

    @staticmethod
    def to_model(aggregate: Owner) -> Any:
        """A new Owner becomes a new row."""
        ...

    @staticmethod
    def to_domain(model: Any) -> Owner:
        """A row is rehydrated into an Owner — through the constructor, so no event is raised."""
        ...

    @staticmethod
    def update_model(model: Any, aggregate: Owner) -> None:
        """A loaded row is brought in line with a mutated Owner."""
        ...
