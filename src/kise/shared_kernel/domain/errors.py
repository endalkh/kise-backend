"""Base domain errors.

Domain errors describe *business* failures and know nothing about HTTP. One handler in the
presentation layer maps them to status codes, so no rule ever mentions a status code.
"""

from __future__ import annotations

from typing import Any


class DomainError(Exception):
    """Base class for every failure raised by the domain layer."""

    code = "domain_error"

    def __init__(self, message: str, **detail: Any) -> None:
        super().__init__(message)
        self.message = message
        self.detail: dict[str, Any] = detail


class InvariantViolation(DomainError):
    """An aggregate was asked to enter a state its rules forbid."""

    code = "invariant_violation"


class ValidationError(DomainError):
    """A value object was handed input it cannot represent."""

    code = "validation_error"


class NotFound(DomainError):
    """An aggregate was looked up by id and does not exist for this owner."""

    code = "not_found"


class Conflict(DomainError):
    """The operation clashes with something that already exists."""

    code = "conflict"


class PermissionDenied(DomainError):
    """The caller is not the owner of the record."""

    code = "permission_denied"
