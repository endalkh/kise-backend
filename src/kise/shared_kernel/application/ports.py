"""Technical ports shared by every context.

These are the seams where the application layer stops and the machine starts. Each one exists
because a use case needs the *capability* without wanting the mechanism: a rule that needs today's
date must not reach for ``date.today()``, or it becomes untestable.

Implementations live in ``platform/``.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Callable, Iterable, Sequence
from datetime import date, datetime
from types import TracebackType
from typing import Protocol, runtime_checkable

from kise.shared_kernel.domain.events import DomainEvent


class Clock(ABC):
    """Where the application gets "now" from.

    A port, not a convenience: `Clock` is what lets a test place an expense in ጳጉሜን 2019 without
    waiting for September 2027.
    """

    @abstractmethod
    def now(self) -> datetime:
        """The current instant, timezone-aware."""

    @abstractmethod
    def today(self) -> date:
        """The current Gregorian date."""


class EventBus(ABC):
    """Dispatches domain events to their handlers, after the transaction commits."""

    @abstractmethod
    def subscribe(
        self, event_type: type[DomainEvent], handler: Callable[[DomainEvent], None]
    ) -> None:
        """Register a handler for one event type."""

    @abstractmethod
    def publish(self, events: Iterable[DomainEvent]) -> None:
        """Hand events to their handlers, in the order they happened."""


@runtime_checkable
class TransactionParticipant(Protocol):
    """Something the Unit of Work must talk to before committing.

    Repositories implement this: because aggregates and rows are separate objects, a mutated
    aggregate has to be written back onto its row, and its recorded events have to be collected.
    Declared structurally so the application layer never imports a repository implementation.
    """

    def synchronise(self) -> None:
        """Write every tracked aggregate's state back onto its row."""
        ...

    def collect_events(self) -> Sequence[DomainEvent]:
        """Drain the events recorded by tracked aggregates."""
        ...


class UnitOfWork(ABC):
    """One business transaction.

    Everything a use case does either commits together or not at all. Domain events are dispatched
    **after** a successful commit, so a handler never reacts to work that rolled back.
    """

    def __enter__(self) -> UnitOfWork:
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        if exc_type is not None:
            self.rollback()

    @abstractmethod
    def register(self, participant: TransactionParticipant) -> None:
        """Enlist a repository in this transaction."""

    @abstractmethod
    def flush(self) -> None:
        """Send pending statements without ending the transaction."""

    @abstractmethod
    def commit(self) -> None:
        """Synchronise aggregates onto rows, commit, then publish the collected events."""

    @abstractmethod
    def rollback(self) -> None:
        """Abandon everything done in this transaction."""
