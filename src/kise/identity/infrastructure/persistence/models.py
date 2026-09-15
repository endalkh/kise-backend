"""Database models owned by the **Identity** context.

Rows, not aggregates. No rules, no validation, no behaviour: every invariant is enforced in
``identity/domain/models/owner.py`` before a mapper hands anything to this class. The domain never
imports this module, and the architecture test proves it.
"""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from sqlalchemy import DateTime, String, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from kise.platform.database import Base

__all__ = ["OwnerModel"]


class OwnerModel(Base):
    """One account."""

    __tablename__ = "owners"

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True)
    email: Mapped[str] = mapped_column(String(254), unique=True, index=True)
    password_hash: Mapped[str] = mapped_column(String(255))
    display_name: Mapped[str] = mapped_column(String(60))
    preferred_calendar: Mapped[str] = mapped_column(String(10))
    preferred_language: Mapped[str] = mapped_column(String(2))
    currency: Mapped[str] = mapped_column(String(3))
    registered_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))

    def __repr__(self) -> str:  # pragma: no cover - debugging aid
        return f"OwnerModel(id={self.id}, email={self.email!r})"
