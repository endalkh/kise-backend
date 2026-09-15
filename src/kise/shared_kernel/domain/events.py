"""Domain events.

Events are how bounded contexts talk without importing each other: Identity raises
``OwnerRegistered``, Expense Tracking subscribes and seeds the default categories. They are plain
frozen dataclasses. The Unit of Work pulls them off the aggregates and dispatches them *after* a
successful commit, so a handler never runs for work that rolled back.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from uuid import UUID, uuid4


@dataclass(frozen=True, slots=True, kw_only=True)
class DomainEvent:
    """Something that happened in the domain, named in the past tense."""

    event_id: UUID = field(default_factory=uuid4)
    occurred_at: datetime = field(default_factory=lambda: datetime.now(UTC))

    @property
    def name(self) -> str:
        return type(self).__name__
