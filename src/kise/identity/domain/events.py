"""Events published by the Identity context."""

from __future__ import annotations

from dataclasses import dataclass

from kise.shared_kernel.domain.calendar.calendar_kind import Language
from kise.shared_kernel.domain.events import DomainEvent
from kise.shared_kernel.domain.identifiers import OwnerId


@dataclass(frozen=True, slots=True, kw_only=True)
class OwnerRegistered(DomainEvent):
    """A new account exists.

    Expense Tracking subscribes to this to seed the default categories, which is why the event
    carries the language and currency: the subscriber needs them and must not reach into Identity.
    """

    owner_id: OwnerId
    email: str
    display_name: str
    language: Language
    currency: str
