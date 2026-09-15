"""The Unit of Work: one session, one transaction, events published only after a successful commit.

``commit()`` runs in a fixed order, and the order is the point:

1. **synchronise** — every tracked aggregate's state is written onto its row. Aggregates and rows
   are separate objects, so without this step a mutation would simply be forgotten.
2. **collect** — events recorded by those aggregates are drained *before* the commit, while the
   aggregates are still in hand.
3. **commit** — one transaction for everything the use case did.
4. **publish** — handlers run last. If step 3 raised, they never run at all, so nothing reacts to
   work that was rolled back.
"""

from __future__ import annotations

from collections.abc import Sequence

from sqlalchemy.orm import Session, sessionmaker

from kise.expense_tracking.infrastructure.persistence.repositories import (
    SqlAlchemyCategoryRepository,
    SqlAlchemyExpenseRepository,
    SqlAlchemyFixedExpenseRepository,
    SqlAlchemyItemRepository,
    SqlAlchemyUnitOfMeasurementRepository,
)
from kise.identity.infrastructure.persistence.repository import SqlAlchemyOwnerRepository
from kise.shared_kernel.application.ports import (
    EventBus,
    TransactionParticipant,
    UnitOfWork,
)
from kise.shared_kernel.domain.events import DomainEvent


class SqlAlchemyUnitOfWork(UnitOfWork):
    """Transaction boundary over one SQLAlchemy session."""

    def __init__(self, session: Session, event_bus: EventBus | None = None) -> None:
        self._session = session
        self._event_bus = event_bus
        self._participants: list[TransactionParticipant] = []
        self._published: list[DomainEvent] = []

    @property
    def session(self) -> Session:
        return self._session

    def register(self, participant: TransactionParticipant) -> None:
        if participant not in self._participants:
            self._participants.append(participant)

    def flush(self) -> None:
        for participant in self._participants:
            participant.synchronise()
        self._session.flush()

    def commit(self) -> None:
        for participant in self._participants:
            participant.synchronise()
        events = self._drain_events()
        self._session.commit()
        self._publish(events)

    def rollback(self) -> None:
        self._session.rollback()

    def _drain_events(self) -> list[DomainEvent]:
        events: list[DomainEvent] = []
        for participant in self._participants:
            events.extend(participant.collect_events())
        return events

    def _publish(self, events: Sequence[DomainEvent]) -> None:
        self._published.extend(events)
        if self._event_bus is not None and events:
            self._event_bus.publish(events)

    @property
    def published_events(self) -> tuple[DomainEvent, ...]:
        """Everything published in this transaction. Exposed for tests to assert on."""
        return tuple(self._published)


class KiseUnitOfWork(SqlAlchemyUnitOfWork):
    """The Unit of Work the application actually uses, with every repository attached.

    This class is allowed to know all three contexts because ``platform/`` is the composition root —
    the one place where wiring lives. The contexts themselves stay ignorant of each other.
    """

    def __init__(self, session: Session, event_bus: EventBus | None = None) -> None:
        super().__init__(session, event_bus)
        self.owners = SqlAlchemyOwnerRepository(session)
        self.categories = SqlAlchemyCategoryRepository(session)
        self.expenses = SqlAlchemyExpenseRepository(session)
        self.fixed_expenses = SqlAlchemyFixedExpenseRepository(session)
        self.units = SqlAlchemyUnitOfMeasurementRepository(session)
        self.items = SqlAlchemyItemRepository(session)
        for repository in (
            self.owners,
            self.categories,
            self.expenses,
            self.fixed_expenses,
            self.units,
            self.items,
        ):
            self.register(repository)


def build_unit_of_work_factory(
    session_factory: sessionmaker[Session], event_bus: EventBus | None = None
):
    """Return a callable that opens a fresh Unit of Work per request."""

    def factory() -> KiseUnitOfWork:
        return KiseUnitOfWork(session_factory(), event_bus)

    return factory
