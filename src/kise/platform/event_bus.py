"""An in-process, synchronous event bus.

Roughly thirty lines, and that is the right size for v1: no broker, no queue, no retries. Its whole
job is to let Identity announce ``OwnerRegistered`` without knowing that Expense Tracking exists and
seeds ten categories in response.
"""

from __future__ import annotations

import logging
from collections import defaultdict
from collections.abc import Callable, Iterable

from kise.shared_kernel.application.ports import EventBus
from kise.shared_kernel.domain.events import DomainEvent

logger = logging.getLogger("kise.events")

Handler = Callable[[DomainEvent], None]


class InProcessEventBus(EventBus):
    """Dispatches each event to the handlers registered for its exact type."""

    def __init__(self, *, swallow_handler_errors: bool = False) -> None:
        self._handlers: dict[type[DomainEvent], list[Handler]] = defaultdict(list)
        # A failing subscriber must not undo a committed transaction, but during development a
        # silent handler failure is worse than a loud one — so this is opt-in.
        self._swallow_handler_errors = swallow_handler_errors

    def subscribe(self, event_type: type[DomainEvent], handler: Handler) -> None:
        self._handlers[event_type].append(handler)

    def publish(self, events: Iterable[DomainEvent]) -> None:
        for event in events:
            for handler in self._handlers.get(type(event), ()):
                try:
                    handler(event)
                except Exception:
                    logger.exception("Handler failed for %s", event.name)
                    if not self._swallow_handler_errors:
                        raise

    def handler_count(self, event_type: type[DomainEvent]) -> int:
        """Exposed for tests and for a startup sanity check on the wiring."""
        return len(self._handlers.get(event_type, ()))
