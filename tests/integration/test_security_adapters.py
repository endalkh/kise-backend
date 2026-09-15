"""The credential adapters. Small surface, high consequence, so tested directly."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import jwt
import pytest

from kise.identity.domain.errors import InvalidToken
from kise.identity.domain.models import PasswordHash
from kise.identity.infrastructure.bcrypt_hasher import BcryptPasswordHasher
from kise.identity.infrastructure.jwt_token_service import JwtTokenService
from kise.shared_kernel.domain.errors import ValidationError
from kise.shared_kernel.domain.identifiers import OwnerId

SECRET = "a-secret-long-enough-to-be-taken-seriously"

# The cheapest cost bcrypt accepts: these tests are about behaviour, not about how slow the
# hash is. Production uses the default of 12, set in the container.
hasher = BcryptPasswordHasher(rounds=4)


# -- password hashing ---------------------------------------------------


def test_hashing_then_verifying():
    hashed = hasher.hash("correct horse battery")
    assert isinstance(hashed, PasswordHash)
    assert hasher.verify("correct horse battery", hashed)
    assert not hasher.verify("wrong horse battery", hashed)


def test_the_hash_is_salted():
    """Two identical passwords must not produce the same stored value."""
    first = hasher.hash("same password")
    second = hasher.hash("same password")
    assert first != second
    assert hasher.verify("same password", first)
    assert hasher.verify("same password", second)


def test_the_plaintext_never_appears_in_the_hash():
    hashed = hasher.hash("Sup3rSecret!")
    assert "Sup3rSecret!" not in hashed.value


def test_short_passwords_are_refused():
    with pytest.raises(ValidationError):
        hasher.hash("short")


def test_passwords_longer_than_bcrypt_can_read_are_refused():
    """bcrypt truncates at 72 bytes; accepting a longer password would check only part of it."""
    with pytest.raises(ValidationError):
        hasher.hash("x" * 73)
    # Multi-byte characters count as bytes, which matters for Amharic passphrases.
    with pytest.raises(ValidationError):
        hasher.hash("ሀ" * 25)  # 3 bytes each = 75
    assert hasher.verify("ሀ" * 20, hasher.hash("ሀ" * 20))  # 60 bytes is fine


def test_non_text_is_refused():
    with pytest.raises(ValidationError):
        hasher.hash(12345678)  # type: ignore[arg-type]


def test_a_malformed_stored_hash_reads_as_wrong_password():
    """A corrupt row must fail a login, not crash it."""
    assert not hasher.verify("anything", PasswordHash("not-a-bcrypt-hash"))
    assert not hasher.verify("", hasher.hash("a real password"))


# -- tokens -------------------------------------------------------------


def test_issue_then_read_round_trip():
    service = JwtTokenService(SECRET)
    owner_id = OwnerId.new()
    token = service.issue(owner_id)
    assert service.read(token.value) == owner_id
    assert token.expires_at > datetime.now(UTC)


def test_the_token_object_does_not_print_itself():
    token = JwtTokenService(SECRET).issue(OwnerId.new())
    assert token.value not in repr(token)
    assert token.value not in str(token)


def test_a_token_signed_with_another_secret_is_refused():
    issued = JwtTokenService(SECRET).issue(OwnerId.new())
    with pytest.raises(InvalidToken):
        JwtTokenService("a-completely-different-secret-key-value").read(issued.value)


def test_a_tampered_token_is_refused():
    token = JwtTokenService(SECRET).issue(OwnerId.new()).value
    head, payload, signature = token.split(".")
    with pytest.raises(InvalidToken):
        JwtTokenService(SECRET).read(f"{head}.{payload}.{signature[:-3]}abc")


def test_an_expired_token_is_refused():
    service = JwtTokenService(SECRET, expire_minutes=-1)
    expired = service.issue(OwnerId.new())
    with pytest.raises(InvalidToken):
        service.read(expired.value)


def test_rubbish_is_refused():
    service = JwtTokenService(SECRET)
    for rubbish in ("", "not.a.token", "Bearer something"):
        with pytest.raises(InvalidToken):
            service.read(rubbish)


def test_a_token_without_a_subject_is_refused():
    payload = {"exp": int((datetime.now(UTC) + timedelta(hours=1)).timestamp())}
    forged = jwt.encode(payload, SECRET, algorithm="HS256")
    with pytest.raises(InvalidToken):
        JwtTokenService(SECRET).read(forged)


def test_a_subject_that_is_not_an_owner_id_is_refused():
    payload = {
        "sub": "not-a-uuid",
        "exp": int((datetime.now(UTC) + timedelta(hours=1)).timestamp()),
    }
    forged = jwt.encode(payload, SECRET, algorithm="HS256")
    with pytest.raises(InvalidToken):
        JwtTokenService(SECRET).read(forged)


def test_an_unsigned_token_is_refused():
    """The 'none' algorithm attack: a token with no signature must not be accepted."""
    payload = {
        "sub": str(OwnerId.new()),
        "exp": int((datetime.now(UTC) + timedelta(hours=1)).timestamp()),
    }
    unsigned = jwt.encode(payload, key="", algorithm="none")
    with pytest.raises(InvalidToken):
        JwtTokenService(SECRET).read(unsigned)


def test_a_weak_secret_is_refused_at_construction():
    with pytest.raises(ValueError):
        JwtTokenService("short")
    with pytest.raises(ValueError):
        JwtTokenService("")
