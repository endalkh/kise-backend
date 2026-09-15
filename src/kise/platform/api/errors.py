"""Domain errors, mapped to HTTP in exactly one place.

The domain raises business failures that know nothing about HTTP — ``CategoryNotFound``,
``EmailAlreadyRegistered``, ``InvalidCredentials``. This module is the single seam that turns each
into a status code and the wire error shape ``{"code", "message", "detail"}``. No rule anywhere
else mentions a status code, which is the whole point of keeping the mapping here.

Mapping is by the error's *base* type, so a new ``FooNotFound(NotFound)`` becomes a 404 for free.
The ``code`` on the wire is the specific class's ``code`` attribute, so the client can branch on
``category_name_taken`` even though the status is a generic 409.
"""

from __future__ import annotations

from fastapi import FastAPI, Request, status
from fastapi.responses import JSONResponse

from kise.identity.domain.errors import InvalidCredentials, InvalidToken
from kise.shared_kernel.domain.calendar.ethiopian import EthiopianDateError
from kise.shared_kernel.domain.errors import (
    Conflict,
    DomainError,
    InvariantViolation,
    NotFound,
    PermissionDenied,
    ValidationError,
)

# Order matters: the most specific base classes first, so ``InvalidCredentials`` (a bare
# DomainError) is matched before the DomainError catch-all.
_STATUS_BY_TYPE: tuple[tuple[type[DomainError], int], ...] = (
    (InvalidCredentials, status.HTTP_401_UNAUTHORIZED),
    (InvalidToken, status.HTTP_401_UNAUTHORIZED),
    (PermissionDenied, status.HTTP_403_FORBIDDEN),
    (NotFound, status.HTTP_404_NOT_FOUND),
    (Conflict, status.HTTP_409_CONFLICT),
    (ValidationError, status.HTTP_422_UNPROCESSABLE_ENTITY),
    # An invariant violation is the caller asking for an impossible state (e.g. archiving twice):
    # a 409, because it clashes with the record's current state.
    (InvariantViolation, status.HTTP_409_CONFLICT),
)

_DEFAULT_STATUS = status.HTTP_400_BAD_REQUEST


def status_for(error: DomainError) -> int:
    for error_type, code in _STATUS_BY_TYPE:
        if isinstance(error, error_type):
            return code
    return _DEFAULT_STATUS


def error_body(error: DomainError) -> dict[str, object]:
    return {"code": error.code, "message": error.message, "detail": error.detail}


def install_error_handlers(app: FastAPI) -> None:
    """Register the one handler that turns every domain error into the wire error shape."""

    @app.exception_handler(DomainError)
    async def _handle_domain_error(_: Request, error: DomainError) -> JSONResponse:
        response = JSONResponse(status_code=status_for(error), content=error_body(error))
        if isinstance(error, InvalidCredentials | InvalidToken):
            # RFC 6750: a 401 over bearer auth should say so.
            response.headers["WWW-Authenticate"] = "Bearer"
        return response

    @app.exception_handler(EthiopianDateError)
    async def _handle_ethiopian_date_error(_: Request, error: EthiopianDateError) -> JSONResponse:
        # A calendar value the domain cannot represent (e.g. ጳጉሜን 30) is a validation failure, the
        # same as a bad Gregorian date. It is a ``ValueError`` rather than a ``DomainError`` for
        # historical reasons, so it needs its own line; the wire shape stays identical.
        return JSONResponse(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            content={"code": "validation_error", "message": str(error), "detail": {}},
        )
