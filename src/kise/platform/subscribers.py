"""Event subscribers wired at composition time.

Subscribers are the one legitimate place where one context reacts to another's event. They live in
``platform/`` — the composition root — precisely because reacting across contexts is wiring, and the
contexts themselves must stay ignorant of each other (the architecture test enforces this).

``OwnerRegistered`` is the only event with a subscriber in v1: when a new account exists, Expense
Tracking seeds the ten default categories. Because the Unit of Work publishes events *after* a
successful commit, this handler opens a *fresh* Unit of Work of its own — the owner's transaction is
already closed, and the seeded categories are a separate, self-contained write.
"""

from __future__ import annotations

from collections.abc import Callable

from kise.expense_tracking.domain.models import default_categories_for
from kise.identity.domain.events import OwnerRegistered
from kise.platform.unit_of_work import KiseUnitOfWork
from kise.shared_kernel.domain.events import DomainEvent

UnitOfWorkFactory = Callable[[], KiseUnitOfWork]


def make_seed_default_categories(uow_factory: UnitOfWorkFactory) -> Callable[[DomainEvent], None]:
    """Build the ``OwnerRegistered`` handler, bound to a Unit of Work factory.

    The factory is injected rather than imported so the handler stays testable: a test hands it a
    factory over an in-memory database and asserts the ten categories appear.
    """

    def handle(event: DomainEvent) -> None:
        if not isinstance(event, OwnerRegistered):  # pragma: no cover - defensive
            return
        uow = uow_factory()
        with uow:
            for category in default_categories_for(event.owner_id):
                uow.categories.add(category)
            uow.commit()

    return handle
