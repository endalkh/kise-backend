"""SQLAlchemy implementation of ``OwnerRepository``."""

from __future__ import annotations

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from kise.identity.domain.errors import OwnerNotFound
from kise.identity.domain.models import EmailAddress, Owner
from kise.identity.infrastructure.persistence.mappers import OwnerMapper
from kise.identity.infrastructure.persistence.models import OwnerModel
from kise.shared_kernel.domain.identifiers import OwnerId
from kise.shared_kernel.infrastructure.repository import TrackingRepository


class SqlAlchemyOwnerRepository(TrackingRepository[Owner]):
    mapper = OwnerMapper

    def __init__(self, session: Session) -> None:
        super().__init__(session)

    @classmethod
    def model_type(cls) -> type[OwnerModel]:
        return OwnerModel

    def add(self, owner: Owner) -> None:
        self._insert(owner)

    def get(self, owner_id: OwnerId) -> Owner:
        cached = self._cached(owner_id)
        if cached is not None:
            return cached
        model = self._session.get(OwnerModel, owner_id.value)
        if model is None:
            raise OwnerNotFound("No such account", owner_id=str(owner_id))
        return self._rehydrate(model)

    def find_by_email(self, email: EmailAddress) -> Owner | None:
        model = self._session.scalars(
            select(OwnerModel).where(OwnerModel.email == str(email))
        ).one_or_none()
        return self._rehydrate(model) if model is not None else None

    def email_exists(self, email: EmailAddress) -> bool:
        found = self._session.scalar(
            select(func.count()).select_from(OwnerModel).where(OwnerModel.email == str(email))
        )
        return bool(found)
