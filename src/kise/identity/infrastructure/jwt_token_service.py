"""PyJWT implementation of ``TokenService``."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import jwt

from kise.identity.application.ports import AccessToken, TokenService
from kise.identity.domain.errors import InvalidToken
from kise.shared_kernel.domain.identifiers import OwnerId

ALGORITHM = "HS256"


class JwtTokenService(TokenService):
    """HS256 bearer tokens whose subject is the Owner id."""

    def __init__(self, secret_key: str, *, expire_minutes: int = 60 * 24 * 7) -> None:
        if not secret_key or len(secret_key) < 16:
            raise ValueError("The JWT secret key is too short to be worth having")
        self._secret_key = secret_key
        self._expire = timedelta(minutes=expire_minutes)

    def issue(self, owner_id: OwnerId) -> AccessToken:
        issued_at = datetime.now(UTC)
        expires_at = issued_at + self._expire
        payload = {
            "sub": str(owner_id),
            "iat": int(issued_at.timestamp()),
            "exp": int(expires_at.timestamp()),
        }
        token = jwt.encode(payload, self._secret_key, algorithm=ALGORITHM)
        return AccessToken(token, expires_at)

    def read(self, token: str) -> OwnerId:
        try:
            payload = jwt.decode(token, self._secret_key, algorithms=[ALGORITHM])
        except jwt.ExpiredSignatureError as exc:
            raise InvalidToken("Your session has expired; please sign in again") from exc
        except jwt.InvalidTokenError as exc:
            raise InvalidToken("That token is not valid") from exc

        subject = payload.get("sub")
        if not subject:
            raise InvalidToken("That token identifies nobody")
        try:
            return OwnerId.parse(subject)
        except Exception as exc:  # noqa: BLE001 - any parse failure is the same answer
            raise InvalidToken("That token identifies nobody") from exc
