"""What the Identity service accepts.

Commands carry primitives, because they arrive from outside — an HTTP body, a CLI argument, a test.
Turning those primitives into value objects is the service's first job, so a malformed email is
refused at the edge of the application rather than deep inside a rule.

What the service *returns* lives in ``views.py``.
"""

from __future__ import annotations

from dataclasses import dataclass

from kise.shared_kernel.domain.identifiers import OwnerId


@dataclass(frozen=True, slots=True)
class RegisterOwnerCommand:
    email: str
    password: str
    display_name: str
    calendar: str | None = None
    language: str | None = None
    currency: str | None = None


@dataclass(frozen=True, slots=True)
class AuthenticateOwnerCommand:
    email: str
    password: str


@dataclass(frozen=True, slots=True)
class UpdatePreferencesCommand:
    owner_id: OwnerId
    display_name: str | None = None
    calendar: str | None = None
    language: str | None = None
