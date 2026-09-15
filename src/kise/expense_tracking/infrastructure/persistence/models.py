"""Database models owned by the **Expense Tracking** context.

Rows, not aggregates. Every invariant is enforced in ``expense_tracking/domain/models/`` before a
mapper hands anything to these classes; the domain never imports this module.

Shape decisions worth knowing:

* ``Money`` is two columns — ``amount_minor`` (integer) plus ``currency``. Never a float.
* ``Period`` is two integer columns, plus a calendar column where it can vary.
* ``settlements`` carries **no** calendar column: a Settlement is always in its commitment's Anchor
  Calendar, so storing it twice would let the two disagree.
* ``categories.name_key`` holds the case-folded name, so the per-Owner uniqueness policy is
  backed by a real unique constraint instead of trusting every code path to check.
* **No relationships between aggregate roots.** There is no ``CategoryModel.owner`` or
  ``ExpenseModel.category`` attribute — crossing an aggregate boundary is done by id, through a
  repository. The one relationship here, ``FixedExpenseModel.settlements``, stays *inside* one
  aggregate.
* ``owner_id`` references ``owners.id``, a table owned by the Identity context. A deliberate
  exception: Kise is one database with one Owner per install, and the foreign key buys cascade
  deletion of everything a person owns when their account goes. The coupling is by table *name*
  only — no Python import crosses the context boundary, which the architecture test enforces.
"""

from __future__ import annotations

from datetime import date
from uuid import UUID

from sqlalchemy import (
    BigInteger,
    Boolean,
    Date,
    ForeignKey,
    Index,
    Integer,
    String,
    UniqueConstraint,
    Uuid,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from kise.platform.database import Base

__all__ = [
    "CategoryModel",
    "ExpenseModel",
    "FixedExpenseModel",
    "ItemModel",
    "SettlementModel",
    "UnitOfMeasurementModel",
]


class CategoryModel(Base):
    """A spending bucket."""

    __tablename__ = "categories"
    __table_args__ = (
        UniqueConstraint("owner_id", "name_key", name="owner_category_name"),
        Index("ix_categories_owner_id_is_archived", "owner_id", "is_archived"),
    )

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True)
    owner_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("owners.id", ondelete="CASCADE"), index=True
    )
    name: Mapped[str] = mapped_column(String(60))
    name_key: Mapped[str] = mapped_column(String(60))
    name_am: Mapped[str | None] = mapped_column(String(60), nullable=True)
    color: Mapped[str] = mapped_column(String(7))
    icon: Mapped[str | None] = mapped_column(String(40), nullable=True)
    is_archived: Mapped[bool] = mapped_column(Boolean, default=False)
    is_default: Mapped[bool] = mapped_column(Boolean, default=False)

    def __repr__(self) -> str:  # pragma: no cover - debugging aid
        return f"CategoryModel(id={self.id}, name={self.name!r})"


class ExpenseModel(Base):
    """One Dynamic Expense."""

    __tablename__ = "expenses"
    __table_args__ = (
        # The index every listing and every monthly report uses.
        Index("ix_expenses_owner_id_spent_on", "owner_id", "spent_on"),
    )

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True)
    owner_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("owners.id", ondelete="CASCADE"), index=True
    )
    category_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("categories.id"), index=True
    )
    amount_minor: Mapped[int] = mapped_column(BigInteger)
    currency: Mapped[str] = mapped_column(String(3))
    spent_on: Mapped[date] = mapped_column(Date)
    entered_in: Mapped[str] = mapped_column(String(10))
    note: Mapped[str | None] = mapped_column(String(500), nullable=True)
    payment_method: Mapped[str] = mapped_column(String(10))
    # The optional item line: what was bought, how much (integer thousandths), and in what unit.
    # All three are null together for a plain amount-only expense.
    item_id: Mapped[UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("items.id"), nullable=True, index=True
    )
    quantity_milli: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    unit_id: Mapped[UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("unit_of_measurements.id"), nullable=True, index=True
    )

    def __repr__(self) -> str:  # pragma: no cover - debugging aid
        return f"ExpenseModel(id={self.id}, amount_minor={self.amount_minor})"


class FixedExpenseModel(Base):
    """A Fixed Monthly Expense — the root of its aggregate."""

    __tablename__ = "fixed_expenses"

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True)
    owner_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("owners.id", ondelete="CASCADE"), index=True
    )
    category_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("categories.id"), index=True
    )
    title: Mapped[str] = mapped_column(String(80))
    amount_minor: Mapped[int] = mapped_column(BigInteger)
    currency: Mapped[str] = mapped_column(String(3))
    anchor_calendar: Mapped[str] = mapped_column(String(10))
    start_year: Mapped[int] = mapped_column(Integer)
    start_month: Mapped[int] = mapped_column(Integer)
    end_year: Mapped[int | None] = mapped_column(Integer, nullable=True)
    end_month: Mapped[int | None] = mapped_column(Integer, nullable=True)
    due_day: Mapped[int] = mapped_column(Integer)
    note: Mapped[str | None] = mapped_column(String(500), nullable=True)
    is_paused: Mapped[bool] = mapped_column(Boolean, default=False)

    settlements: Mapped[list[SettlementModel]] = relationship(
        back_populates="fixed_expense",
        cascade="all, delete-orphan",
        # Settlements are part of the aggregate, so they load with the root, always.
        lazy="selectin",
    )

    def __repr__(self) -> str:  # pragma: no cover - debugging aid
        return f"FixedExpenseModel(id={self.id}, title={self.title!r})"


class SettlementModel(Base):
    """Proof that one Period of a commitment was paid.

    A child row inside the FixedExpense aggregate — never loaded on its own by a repository.
    """

    __tablename__ = "settlements"
    __table_args__ = (
        # The one-Settlement-per-Period invariant, backstopped in the schema.
        UniqueConstraint(
            "fixed_expense_id", "period_year", "period_month", name="one_settlement_per_period"
        ),
    )

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True)
    fixed_expense_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("fixed_expenses.id", ondelete="CASCADE"), index=True
    )
    owner_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), index=True)
    period_year: Mapped[int] = mapped_column(Integer)
    period_month: Mapped[int] = mapped_column(Integer)
    amount_minor: Mapped[int] = mapped_column(BigInteger)
    currency: Mapped[str] = mapped_column(String(3))
    settled_on: Mapped[date] = mapped_column(Date)

    fixed_expense: Mapped[FixedExpenseModel] = relationship(back_populates="settlements")

    def __repr__(self) -> str:  # pragma: no cover - debugging aid
        return f"SettlementModel(id={self.id}, period={self.period_year}-{self.period_month})"


class UnitOfMeasurementModel(Base):
    """A unit of measurement — kg, litre, piece. Global (shared across owners), seeded on first run.

    ``code`` is the stable identity and is unique across the whole table; ``is_system`` marks the
    seeded set, which cannot be deleted.
    """

    __tablename__ = "unit_of_measurements"
    __table_args__ = (UniqueConstraint("code", name="unit_code_unique"),)

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True)
    code: Mapped[str] = mapped_column(String(16))
    name: Mapped[str] = mapped_column(String(40))
    name_am: Mapped[str | None] = mapped_column(String(40), nullable=True)
    is_system: Mapped[bool] = mapped_column(Boolean, default=False)

    def __repr__(self) -> str:  # pragma: no cover - debugging aid
        return f"UnitOfMeasurementModel(id={self.id}, code={self.code!r})"


class ItemModel(Base):
    """A thing the Owner buys, tracked across expenses. Owner-scoped and name-unique per Owner."""

    __tablename__ = "items"
    __table_args__ = (
        UniqueConstraint("owner_id", "name_key", name="owner_item_name"),
        Index("ix_items_owner_id_is_archived", "owner_id", "is_archived"),
    )

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True)
    owner_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("owners.id", ondelete="CASCADE"), index=True
    )
    name: Mapped[str] = mapped_column(String(60))
    name_key: Mapped[str] = mapped_column(String(60))
    name_am: Mapped[str | None] = mapped_column(String(60), nullable=True)
    default_unit_id: Mapped[UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("unit_of_measurements.id"), nullable=True
    )
    is_archived: Mapped[bool] = mapped_column(Boolean, default=False)

    def __repr__(self) -> str:  # pragma: no cover - debugging aid
        return f"ItemModel(id={self.id}, name={self.name!r})"
