"""The Identity application service.

One service per aggregate, and it is the only thing the presentation layer talks to. A router calls
``OwnerService.register(...)`` and gets back a plain result; it never sees a repository, a mapper or
a row.

The service is the transaction boundary. Each public method is one business operation: it resolves
the primitives it was handed into value objects, asks the aggregate to do the work, and commits.
Rules stay in the aggregate — this layer coordinates, it does not decide.
"""

from __future__ import annotations

from kise.identity.application.commands import (
    AuthenticateOwnerCommand,
    RegisterOwnerCommand,
    UpdatePreferencesCommand,
)
from kise.identity.application.ports import PasswordHasher, TokenService
from kise.identity.application.views import (
    AuthenticatedOwner,
    OwnerProfile,
)
from kise.identity.domain.errors import EmailAlreadyRegistered, InvalidCredentials
from kise.identity.domain.models import EmailAddress, Owner, Preferences
from kise.identity.infrastructure.persistence.repository import SqlAlchemyOwnerRepository
from kise.shared_kernel.application.ports import Clock, UnitOfWork
from kise.shared_kernel.domain.identifiers import OwnerId


class OwnerService:
    """Everything a person can do to their own account."""

    def __init__(
        self,
        owners: SqlAlchemyOwnerRepository,
        hasher: PasswordHasher,
        tokens: TokenService,
        clock: Clock,
        uow: UnitOfWork,
    ) -> None:
        self._owners = owners
        self._hasher = hasher
        self._tokens = tokens
        self._clock = clock
        self._uow = uow

    # -- commands -------------------------------------------------------
    def register(self, command: RegisterOwnerCommand) -> AuthenticatedOwner:
        """Create an account and sign in, so registering is one round trip."""
        email = EmailAddress(command.email)
        # Checked here rather than left to the unique index, so the caller gets a sentence instead
        # of a constraint name. The index is still the last word.
        if self._owners.email_exists(email):
            raise EmailAlreadyRegistered(str(email))

        preferences = Preferences(
            **{
                key: value
                for key, value in (
                    ("calendar", command.calendar),
                    ("language", command.language),
                    ("currency", command.currency),
                )
                if value is not None
            }
        )
        owner = Owner.register(
            email=email,
            password_hash=self._hasher.hash(command.password),
            display_name=command.display_name,
            registered_at=self._clock.now(),
            preferences=preferences,
        )
        self._owners.add(owner)
        # Committing publishes OwnerRegistered, which is what seeds the default categories.
        self._uow.commit()
        return AuthenticatedOwner(self._profile(owner), self._tokens.issue(owner.id))

    def authenticate(self, command: AuthenticateOwnerCommand) -> AuthenticatedOwner:
        """Sign in. A wrong password and an unknown account give the same answer, on purpose."""
        try:
            email = EmailAddress(command.email)
        except Exception as exc:  # noqa: BLE001 - a malformed email is just a failed sign-in
            raise InvalidCredentials from exc

        owner = self._owners.find_by_email(email)
        if owner is None or not self._hasher.verify(command.password, owner.password_hash):
            raise InvalidCredentials
        return AuthenticatedOwner(self._profile(owner), self._tokens.issue(owner.id))

    def update_preferences(self, command: UpdatePreferencesCommand) -> OwnerProfile:
        """Change the display name, calendar or language.

        Currency is not here: changing it is only safe before anything has been recorded, which is
        knowledge this service does not have. See ``Owner.change_currency``.
        """
        owner = self._owners.get(command.owner_id)
        if command.display_name is not None:
            owner.rename(command.display_name)
        if command.calendar is not None:
            owner.prefer_calendar(command.calendar)
        if command.language is not None:
            owner.prefer_language(command.language)
        self._uow.commit()
        return self._profile(owner)

    # -- queries --------------------------------------------------------
    def profile(self, owner_id: OwnerId) -> OwnerProfile:
        return self._profile(self._owners.get(owner_id))

    def owner_for_token(self, token: str) -> OwnerProfile:
        """Resolve a bearer token to a profile. Used by the API's auth dependency."""
        return self.profile(self._tokens.read(token))

    # -- internals ------------------------------------------------------
    @staticmethod
    def _profile(owner: Owner) -> OwnerProfile:
        return OwnerProfile(
            owner_id=owner.id,
            email=str(owner.email),
            display_name=owner.display_name,
            calendar=owner.preferences.calendar,
            language=owner.preferences.language,
            currency=owner.preferences.currency,
            registered_at=owner.registered_at,
        )
