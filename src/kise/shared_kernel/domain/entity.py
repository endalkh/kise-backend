"""Entity and aggregate-root bases.

Identity is by id, not by attribute values — two Expense objects with the same id are the same
Expense even if one has been edited. Value objects (Money, Period, SpendDate) are the opposite:
they are compared by value and are immutable.
"""

from __future__ import annotations

from kise.shared_kernel.domain.events import DomainEvent
from kise.shared_kernel.domain.identifiers import EntityId


class Entity:
    """An object with a lifecycle and an identity."""

    def __init__(self, entity_id: EntityId) -> None:
        self._id = entity_id

    @property
    def id(self) -> EntityId:
        return self._id

    def __eq__(self, other: object) -> bool:
        if type(other) is not type(self):
            return NotImplemented
        return self._id == other._id  # type: ignore[attr-defined]

    def __hash__(self) -> int:
        return hash((type(self).__name__, self._id))

    def __repr__(self) -> str:  # pragma: no cover - debugging aid
        return f"{type(self).__name__}(id={self._id})"


class AggregateRoot(Entity):
    """The only entity in an aggregate that the outside world may hold a reference to.

    All changes to an aggregate go through its root, which is what makes its invariants
    enforceable. Events recorded here are drained by the Unit of Work after commit.
    """

    def __init__(self, entity_id: EntityId) -> None:
        super().__init__(entity_id)
        self._events: list[DomainEvent] = []

    def record_event(self, event: DomainEvent) -> None:
        self._events.append(event)

    def pull_events(self) -> list[DomainEvent]:
        """Return and clear the recorded events."""
        events, self._events = self._events, []
        return events

    @property
    def has_pending_events(self) -> bool:
        return bool(self._events)
