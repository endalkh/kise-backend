"""bcrypt implementation of ``PasswordHasher``."""

from __future__ import annotations

import bcrypt

from kise.identity.application.ports import PasswordHasher
from kise.identity.domain.models import PasswordHash
from kise.shared_kernel.domain.errors import ValidationError

#: bcrypt silently truncates at 72 bytes, so a longer password would be accepted and then only
#: partly checked. Refusing is honest; the limit is far above anything a person types.
MAX_PASSWORD_BYTES = 72
MIN_PASSWORD_LENGTH = 8


class BcryptPasswordHasher(PasswordHasher):
    """Salted bcrypt. The cost factor is configurable so tests can run at the cheapest setting."""

    def __init__(self, rounds: int = 12) -> None:
        self._rounds = rounds

    def hash(self, plaintext: str) -> PasswordHash:
        self._validate(plaintext)
        digest = bcrypt.hashpw(plaintext.encode("utf-8"), bcrypt.gensalt(rounds=self._rounds))
        return PasswordHash(digest.decode("utf-8"))

    def verify(self, plaintext: str, hashed: PasswordHash) -> bool:
        if not isinstance(plaintext, str) or not plaintext:
            return False
        try:
            return bcrypt.checkpw(plaintext.encode("utf-8"), hashed.value.encode("utf-8"))
        except (ValueError, TypeError):
            # A malformed stored hash must read as "wrong password", not crash a login.
            return False

    @staticmethod
    def _validate(plaintext: str) -> None:
        if not isinstance(plaintext, str):
            raise ValidationError("Password must be text", field="password")
        if len(plaintext) < MIN_PASSWORD_LENGTH:
            raise ValidationError(
                f"Password must be at least {MIN_PASSWORD_LENGTH} characters", field="password"
            )
        if len(plaintext.encode("utf-8")) > MAX_PASSWORD_BYTES:
            raise ValidationError(
                f"Password must be at most {MAX_PASSWORD_BYTES} bytes", field="password"
            )
