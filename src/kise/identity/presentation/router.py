"""The auth router: register, login, and the signed-in owner's profile.

Every handler is thin by design. It maps the request to a command, calls the one service method,
and maps the result back to a response — no rules, no persistence, no branching on domain state.
Domain errors raised by the service (``EmailAlreadyRegistered``, ``InvalidCredentials``) propagate
to the single error handler, which turns them into 409 / 401.
"""

from __future__ import annotations

from fastapi import APIRouter, status

from kise.identity.presentation.schemas import (
    AuthResponse,
    LoginRequest,
    ProfileResponse,
    RegisterRequest,
    UpdateProfileRequest,
)
from kise.platform.api.dependencies import CurrentOwner, ServicesDep

router = APIRouter(prefix="/api/auth", tags=["auth"])


@router.post("/register", response_model=AuthResponse, status_code=status.HTTP_201_CREATED)
def register(request: RegisterRequest, services: ServicesDep) -> AuthResponse:
    """Create an account and sign in, so registering is one round trip.

    Committing publishes ``OwnerRegistered``, which seeds the ten default categories.
    """
    authenticated = services.owners.register(request.to_command())
    return AuthResponse.of(authenticated)


@router.post("/login", response_model=AuthResponse)
def login(request: LoginRequest, services: ServicesDep) -> AuthResponse:
    """Sign in. A wrong password and an unknown account give the same 401, on purpose."""
    authenticated = services.owners.authenticate(request.to_command())
    return AuthResponse.of(authenticated)


@router.get("/me", response_model=ProfileResponse)
def me(current_owner: CurrentOwner) -> ProfileResponse:
    """The signed-in owner's profile. ``get_current_owner`` already resolved the token."""
    return ProfileResponse.of(current_owner)


@router.patch("/me", response_model=ProfileResponse)
def update_me(
    request: UpdateProfileRequest, current_owner: CurrentOwner, services: ServicesDep
) -> ProfileResponse:
    """Change display name, calendar or language. Currency is deliberately not editable here."""
    profile = services.owners.update_preferences(request.to_command(current_owner.owner_id))
    return ProfileResponse.of(profile)
