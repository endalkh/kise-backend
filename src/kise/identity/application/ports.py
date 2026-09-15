"""Ports the Identity application layer depends on.

Both exist so that no rule ever contains a hashing algorithm or a token format. The domain holds a
``PasswordHash`` value object and nothing else about credentials.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime

from kise.identity.domain.models import PasswordHash
from kise.shared_kernel.domain.identifiers import OwnerId


class PasswordHasher(ABC):
    """Turns a plaintext password into a hash, and checks one against a hash."""

    @abstractmethod
    def hash(self, plaintext: str) -> PasswordHash:
        """Hash a password. Implementations must salt."""

    @abstractmethod
    def verify(self, plaintext: str, hashed: PasswordHash) -> bool:
        """Whether the password matches. Must not raise on a malformed hash."""


@dataclass(frozen=True, slots=True)
class AccessToken:
    """A bearer token and when it stops working."""

    value: str
    expires_at: datetime

    def __str__(self) -> str:  # pragma: no cover - keep tokens out of logs
        return "<access token>"

    __repr__ = __str__


class TokenService(ABC):
    """Issues and reads bearer tokens."""

    @abstractmethod
    def issue(self, owner_id: OwnerId) -> AccessToken:
        """Mint a token identifying this Owner."""

    @abstractmethod
    def read(self, token: str) -> OwnerId:
        """Return the Owner the token identifies, or raise ``InvalidToken``."""
