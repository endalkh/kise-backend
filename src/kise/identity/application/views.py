"""What the Identity service returns.

``OwnerProfile`` is what the settings screen shows. ``AuthenticatedOwner`` pairs it with the token
that proves it, so registering and signing in are each a single round trip.

What the service *accepts* lives in ``commands.py``.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from kise.identity.application.ports import AccessToken
from kise.shared_kernel.domain.calendar.calendar_kind import CalendarKind, Language
from kise.shared_kernel.domain.identifiers import OwnerId


@dataclass(frozen=True, slots=True)
class OwnerProfile:
    """What the app shows on the settings screen."""

    owner_id: OwnerId
    email: str
    display_name: str
    calendar: CalendarKind
    language: Language
    currency: str
    registered_at: datetime


@dataclass(frozen=True, slots=True)
class AuthenticatedOwner:
    """A profile plus the token that proves it."""

    profile: OwnerProfile
    token: AccessToken
