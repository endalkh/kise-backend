"""The Owner aggregate — who the account belongs to and how they want to see it.

Identity knows nothing about money. It holds credentials and presentation preferences, and it
announces ``OwnerRegistered`` so that Expense Tracking can seed the default categories without
either context importing the other.
"""

from __future__ import annotations

from datetime import datetime

from kise.identity.domain.events import OwnerRegistered
from kise.identity.domain.value_objects import (
    EmailAddress,
    PasswordHash,
    Preferences,
    clean_display_name,
)
from kise.shared_kernel.domain.calendar.calendar_kind import CalendarKind, Language
from kise.shared_kernel.domain.entity import AggregateRoot
from kise.shared_kernel.domain.errors import InvariantViolation, ValidationError
from kise.shared_kernel.domain.identifiers import OwnerId


class Owner(AggregateRoot):
    """Aggregate root for one person's account."""

    def __init__(
        self,
        owner_id: OwnerId,
        *,
        email: EmailAddress,
        password_hash: PasswordHash,
        display_name: str,
        preferences: Preferences,
        registered_at: datetime,
    ) -> None:
        super().__init__(owner_id)
        if not isinstance(email, EmailAddress):
            raise ValidationError("email must be an EmailAddress")
        if not isinstance(password_hash, PasswordHash):
            raise ValidationError("password_hash must be a PasswordHash")
        if not isinstance(preferences, Preferences):
            raise ValidationError("preferences must be a Preferences")
        self._email = email
        self._password_hash = password_hash
        self._display_name = clean_display_name(display_name)
        self._preferences = preferences
        self._registered_at = registered_at

    # -- construction ---------------------------------------------------
    @classmethod
    def register(
        cls,
        *,
        email: EmailAddress,
        password_hash: PasswordHash,
        display_name: str,
        registered_at: datetime,
        preferences: Preferences | None = None,
        owner_id: OwnerId | None = None,
    ) -> Owner:
        """Create a new Owner and announce it.

        ``registered_at`` is passed in rather than read from the system clock, so the domain stays
        deterministic and testable — time comes from the ``Clock`` port.
        """
        owner = cls(
            owner_id or OwnerId.new(),
            email=email,
            password_hash=password_hash,
            display_name=display_name,
            preferences=preferences or Preferences(),
            registered_at=registered_at,
        )
        owner.record_event(
            OwnerRegistered(
                owner_id=owner.id,
                email=str(owner.email),
                display_name=owner.display_name,
                language=owner.preferences.language,
                currency=owner.preferences.currency,
            )
        )
        return owner

    # -- state ----------------------------------------------------------
    @property
    def id(self) -> OwnerId:
        return self._id  # type: ignore[return-value]

    @property
    def email(self) -> EmailAddress:
        return self._email

    @property
    def password_hash(self) -> PasswordHash:
        return self._password_hash

    @property
    def display_name(self) -> str:
        return self._display_name

    @property
    def preferences(self) -> Preferences:
        return self._preferences

    @property
    def registered_at(self) -> datetime:
        return self._registered_at

    @property
    def currency(self) -> str:
        return self._preferences.currency

    # -- behaviour ------------------------------------------------------
    def rename(self, display_name: str) -> None:
        self._display_name = clean_display_name(display_name)

    def update_preferences(self, preferences: Preferences) -> None:
        if not isinstance(preferences, Preferences):
            raise ValidationError("preferences must be a Preferences")
        self._preferences = preferences

    def prefer_calendar(self, calendar: CalendarKind | str) -> None:
        self._preferences = self._preferences.with_calendar(calendar)

    def prefer_language(self, language: Language | str) -> None:
        self._preferences = self._preferences.with_language(language)

    def change_password(self, password_hash: PasswordHash) -> None:
        if not isinstance(password_hash, PasswordHash):
            raise ValidationError("password_hash must be a PasswordHash")
        if password_hash == self._password_hash:
            raise InvariantViolation("The new password must differ from the current one")
        self._password_hash = password_hash

    def change_currency(self, currency: str) -> None:
        """Change the reporting currency.

        Kise v1 is single-currency per Owner: existing records keep the currency they were written
        in, so this is only allowed before anything has been recorded. The use case checks that,
        because "has this Owner recorded anything?" is not knowledge this aggregate holds.
        """
        self._preferences = self._preferences.with_currency(currency)
