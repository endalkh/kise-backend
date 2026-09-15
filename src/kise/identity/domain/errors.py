"""Failures the Identity context can raise."""

from __future__ import annotations

from kise.shared_kernel.domain.errors import Conflict, DomainError, NotFound


class OwnerNotFound(NotFound):
    code = "owner_not_found"


class EmailAlreadyRegistered(Conflict):
    code = "email_already_registered"

    def __init__(self, email: str) -> None:
        super().__init__("That email address is already registered", email=email)


class InvalidCredentials(DomainError):
    """Wrong email or wrong password — deliberately indistinguishable to the caller."""

    code = "invalid_credentials"

    def __init__(self) -> None:
        super().__init__("Email or password is incorrect")


class InvalidToken(DomainError):
    """The bearer token is missing, malformed, or expired."""

    code = "invalid_token"


class CurrencyChangeNotAllowed(DomainError):
    code = "currency_change_not_allowed"

    def __init__(self) -> None:
        super().__init__(
            "The currency cannot be changed once expenses have been recorded, because existing "
            "amounts were written in the old currency"
        )
