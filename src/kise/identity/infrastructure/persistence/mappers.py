"""Owner <-> OwnerModel."""

from __future__ import annotations

from kise.identity.domain.models import EmailAddress, Owner, PasswordHash, Preferences
from kise.identity.infrastructure.persistence.models import OwnerModel
from kise.shared_kernel.domain.calendar.calendar_kind import CalendarKind, Language
from kise.shared_kernel.domain.identifiers import OwnerId


class OwnerMapper:
    """Translates the Owner aggregate to and from its row."""

    @staticmethod
    def to_model(owner: Owner) -> OwnerModel:
        return OwnerModel(
            id=owner.id.value,
            email=str(owner.email),
            password_hash=owner.password_hash.value,
            display_name=owner.display_name,
            preferred_calendar=owner.preferences.calendar.value,
            preferred_language=owner.preferences.language.value,
            currency=owner.preferences.currency,
            registered_at=owner.registered_at,
        )

    @staticmethod
    def to_domain(entity: OwnerModel) -> Owner:
        # The constructor, not ``Owner.register``: rehydrating must not re-raise OwnerRegistered.
        return Owner(
            OwnerId(entity.id),
            email=EmailAddress(entity.email),
            password_hash=PasswordHash(entity.password_hash),
            display_name=entity.display_name,
            preferences=Preferences(
                calendar=CalendarKind.parse(entity.preferred_calendar),
                language=Language.parse(entity.preferred_language),
                currency=entity.currency,
            ),
            registered_at=entity.registered_at,
        )

    @staticmethod
    def update_model(entity: OwnerModel, owner: Owner) -> None:
        entity.email = str(owner.email)
        entity.password_hash = owner.password_hash.value
        entity.display_name = owner.display_name
        entity.preferred_calendar = owner.preferences.calendar.value
        entity.preferred_language = owner.preferences.language.value
        entity.currency = owner.preferences.currency
