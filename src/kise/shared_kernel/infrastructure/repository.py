"""The repository base that makes two-model persistence work.

With aggregates and rows as separate objects, SQLAlchemy's dirty tracking cannot see a change made
to an aggregate — it only watches its own instances. Something has to remember which row belongs to
which loaded aggregate and write the changes back before the commit. That is this class.

It keeps a small identity map per transaction, which buys three things:

* loading the same aggregate twice returns the *same* object, so two use cases in one transaction
  cannot fight over separate copies;
* ``synchronise()`` applies ``update_model`` to everything that was loaded or added, so a use case
  never has to remember to "save";
* ``collect_events()`` drains the events recorded by those aggregates, for the Unit of Work to
  publish after the commit.
"""

from __future__ import annotations

from abc import ABC
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any, ClassVar, Generic
from uuid import UUID

from sqlalchemy.orm import Session

from kise.shared_kernel.domain.entity import AggregateRoot
from kise.shared_kernel.domain.events import DomainEvent
from kise.shared_kernel.domain.identifiers import EntityId
from kise.shared_kernel.domain.mapper import AggregateT, Mapper


@dataclass(slots=True)
class _Tracked:
    aggregate: Any
    model: Any


class TrackingRepository(ABC, Generic[AggregateT]):
    """Base for SQLAlchemy repositories that map to and from a separate domain model."""

    #: Set by each subclass to the mapper for its aggregate.
    mapper: ClassVar[Mapper]

    def __init__(self, session: Session) -> None:
        self._session = session
        self._tracked: dict[UUID, _Tracked] = {}

    # -- identity map ---------------------------------------------------
    def _track(self, aggregate: AggregateRoot, model: Any) -> None:
        self._tracked[aggregate.id.value] = _Tracked(aggregate, model)

    def _forget(self, aggregate_id: EntityId) -> None:
        self._tracked.pop(aggregate_id.value, None)

    def _cached(self, aggregate_id: EntityId) -> AggregateT | None:
        found = self._tracked.get(aggregate_id.value)
        return found.aggregate if found else None

    def _rehydrate(self, model: Any) -> AggregateT:
        """Map a row to its aggregate, reusing the tracked instance when there is one."""
        existing = self._tracked.get(model.id)
        if existing is not None:
            return existing.aggregate
        aggregate = self.mapper.to_domain(model)
        self._track(aggregate, model)
        return aggregate

    def _rehydrate_all(self, models: Sequence[Any]) -> list[AggregateT]:
        return [self._rehydrate(model) for model in models]

    def _insert(self, aggregate: AggregateRoot) -> None:
        """Add a new aggregate and flush it.

        The flush is not optional. Aggregate roots have no ORM relationships between them, so
        SQLAlchemy has no dependency graph to order cross-aggregate inserts by — a Category inserted
        before its Owner would fail the foreign key. Flushing here makes the use case's creation
        order the insert order.
        """
        model = self.mapper.to_model(aggregate)
        self._session.add(model)
        self._session.flush()
        self._track(aggregate, model)

    def _delete(self, aggregate: AggregateRoot) -> None:
        tracked = self._tracked.get(aggregate.id.value)
        model = tracked.model if tracked else None
        if model is None:
            model = self._session.get(type(self).model_type(), aggregate.id.value)
        if model is not None:
            self._session.delete(model)
        self._forget(aggregate.id)

    @classmethod
    def model_type(cls) -> type:  # pragma: no cover - overridden by subclasses
        raise NotImplementedError

    # -- TransactionParticipant -----------------------------------------
    def synchronise(self) -> None:
        """Write every tracked aggregate's state back onto its row."""
        for tracked in self._tracked.values():
            self.mapper.update_model(tracked.model, tracked.aggregate)

    def collect_events(self) -> Sequence[DomainEvent]:
        """Drain events from tracked aggregates, oldest aggregate first."""
        events: list[DomainEvent] = []
        for tracked in self._tracked.values():
            aggregate = tracked.aggregate
            if isinstance(aggregate, AggregateRoot):
                events.extend(aggregate.pull_events())
        return events

    @property
    def tracked_count(self) -> int:
        """Exposed for tests: how many aggregates this repository is watching."""
        return len(self._tracked)
