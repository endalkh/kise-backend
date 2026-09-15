"""SQLAlchemy implementations of the Expense Tracking repositories.

Every query is filtered by ``owner_id``. That is the mechanical guarantee behind FR-1.4: even if a
use case forgets to check ownership, a lookup for someone else's id returns nothing rather than
someone else's data.
"""

from __future__ import annotations

from uuid import UUID

from sqlalchemy import Select, func, select
from sqlalchemy.orm import Session

from kise.expense_tracking.application.commands import ExpenseFilter
from kise.expense_tracking.domain.errors import (
    CategoryNotFound,
    ExpenseNotFound,
    FixedExpenseNotFound,
    ItemNotFound,
    UnitNotFound,
)
from kise.expense_tracking.domain.models import (
    Category,
    Expense,
    FixedExpense,
    Item,
    UnitOfMeasurement,
)
from kise.expense_tracking.infrastructure.persistence.mappers import (
    CategoryMapper,
    ExpenseMapper,
    FixedExpenseMapper,
    ItemMapper,
    UnitOfMeasurementMapper,
)
from kise.expense_tracking.infrastructure.persistence.models import (
    CategoryModel,
    ExpenseModel,
    FixedExpenseModel,
    ItemModel,
    UnitOfMeasurementModel,
)
from kise.shared_kernel.domain.identifiers import (
    CategoryId,
    ExpenseId,
    FixedExpenseId,
    ItemId,
    OwnerId,
    UnitId,
)
from kise.shared_kernel.infrastructure.repository import TrackingRepository


class SqlAlchemyCategoryRepository(TrackingRepository[Category]):
    mapper = CategoryMapper

    def __init__(self, session: Session) -> None:
        super().__init__(session)

    @classmethod
    def model_type(cls) -> type[CategoryModel]:
        return CategoryModel

    def add(self, category: Category) -> None:
        self._insert(category)

    def add_all(self, categories: list[Category]) -> None:
        for category in categories:
            self._insert(category)

    def get(self, owner_id: OwnerId, category_id: CategoryId) -> Category:
        model = self._session.scalars(
            select(CategoryModel).where(
                CategoryModel.id == category_id.value,
                CategoryModel.owner_id == owner_id.value,
            )
        ).one_or_none()
        if model is None:
            raise CategoryNotFound("No such category", category_id=str(category_id))
        return self._rehydrate(model)

    def list_for_owner(
        self, owner_id: OwnerId, *, include_archived: bool = False
    ) -> list[Category]:
        statement = select(CategoryModel).where(CategoryModel.owner_id == owner_id.value)
        if not include_archived:
            statement = statement.where(CategoryModel.is_archived.is_(False))
        statement = statement.order_by(CategoryModel.name)
        return self._rehydrate_all(self._session.scalars(statement).all())

    def remove(self, category: Category) -> None:
        self._delete(category)


class SqlAlchemyExpenseRepository(TrackingRepository[Expense]):
    mapper = ExpenseMapper

    def __init__(self, session: Session) -> None:
        super().__init__(session)

    @classmethod
    def model_type(cls) -> type[ExpenseModel]:
        return ExpenseModel

    def add(self, expense: Expense) -> None:
        self._insert(expense)

    def get(self, owner_id: OwnerId, expense_id: ExpenseId) -> Expense:
        model = self._session.scalars(
            select(ExpenseModel).where(
                ExpenseModel.id == expense_id.value,
                ExpenseModel.owner_id == owner_id.value,
            )
        ).one_or_none()
        if model is None:
            raise ExpenseNotFound("No such expense", expense_id=str(expense_id))
        return self._rehydrate(model)

    @staticmethod
    def _apply(criteria: ExpenseFilter, statement: Select) -> Select:
        statement = statement.where(ExpenseModel.owner_id == criteria.owner_id.value)
        if criteria.since is not None:
            statement = statement.where(ExpenseModel.spent_on >= criteria.since)
        if criteria.until is not None:
            statement = statement.where(ExpenseModel.spent_on <= criteria.until)
        if criteria.category_ids:
            statement = statement.where(
                ExpenseModel.category_id.in_([c.value for c in criteria.category_ids])
            )
        return statement

    def list(self, criteria: ExpenseFilter) -> list[Expense]:
        statement = self._apply(criteria, select(ExpenseModel))
        # Newest first, with the id as a tiebreaker so pagination is stable when several
        # expenses share a day — which, for a day of taxis and coffee, they will.
        statement = statement.order_by(ExpenseModel.spent_on.desc(), ExpenseModel.id.desc())
        statement = statement.limit(criteria.limit).offset(criteria.offset)
        return self._rehydrate_all(self._session.scalars(statement).all())

    def count(self, criteria: ExpenseFilter) -> int:
        statement = self._apply(criteria, select(func.count()).select_from(ExpenseModel))
        return int(self._session.scalar(statement) or 0)

    def count_for_category(self, owner_id: OwnerId, category_id: CategoryId) -> int:
        statement = (
            select(func.count())
            .select_from(ExpenseModel)
            .where(
                ExpenseModel.owner_id == owner_id.value,
                ExpenseModel.category_id == category_id.value,
            )
        )
        return int(self._session.scalar(statement) or 0)

    def count_for_item(self, owner_id: OwnerId, item_id: ItemId) -> int:
        statement = (
            select(func.count())
            .select_from(ExpenseModel)
            .where(
                ExpenseModel.owner_id == owner_id.value,
                ExpenseModel.item_id == item_id.value,
            )
        )
        return int(self._session.scalar(statement) or 0)

    def count_for_unit(self, unit_id: UnitId) -> int:
        statement = (
            select(func.count())
            .select_from(ExpenseModel)
            .where(ExpenseModel.unit_id == unit_id.value)
        )
        return int(self._session.scalar(statement) or 0)

    def item_usage(
        self, owner_id: OwnerId, since, until
    ) -> list[tuple[UUID, UUID, int, int, int]]:
        """Aggregate item usage in a Gregorian date window, grouped by (item, unit).

        Returns rows of ``(item_id, unit_id, total_quantity_milli, total_amount_minor, count)`` for
        the owner's expenses that carry an item line and fall in ``[since, until]``. This is the
        read side: it bypasses aggregates and groups in SQL, because summing thousands of rows
        through the domain would be wasteful and the result is a report, not a thing to mutate.
        """
        statement = (
            select(
                ExpenseModel.item_id,
                ExpenseModel.unit_id,
                func.sum(ExpenseModel.quantity_milli),
                func.sum(ExpenseModel.amount_minor),
                func.count(),
            )
            .where(
                ExpenseModel.owner_id == owner_id.value,
                ExpenseModel.item_id.is_not(None),
                ExpenseModel.unit_id.is_not(None),
                ExpenseModel.spent_on >= since,
                ExpenseModel.spent_on <= until,
            )
            .group_by(ExpenseModel.item_id, ExpenseModel.unit_id)
        )
        rows = self._session.execute(statement).all()
        return [
            (item_id, unit_id, int(qty or 0), int(amount or 0), int(count or 0))
            for item_id, unit_id, qty, amount, count in rows
        ]

    def remove(self, expense: Expense) -> None:
        self._delete(expense)


class SqlAlchemyFixedExpenseRepository(TrackingRepository[FixedExpense]):
    mapper = FixedExpenseMapper

    def __init__(self, session: Session) -> None:
        super().__init__(session)

    @classmethod
    def model_type(cls) -> type[FixedExpenseModel]:
        return FixedExpenseModel

    def add(self, commitment: FixedExpense) -> None:
        self._insert(commitment)

    def get(self, owner_id: OwnerId, fixed_expense_id: FixedExpenseId) -> FixedExpense:
        model = self._session.scalars(
            select(FixedExpenseModel).where(
                FixedExpenseModel.id == fixed_expense_id.value,
                FixedExpenseModel.owner_id == owner_id.value,
            )
        ).one_or_none()
        if model is None:
            raise FixedExpenseNotFound(
                "No such fixed monthly expense", fixed_expense_id=str(fixed_expense_id)
            )
        return self._rehydrate(model)

    def list_for_owner(
        self, owner_id: OwnerId, *, include_paused: bool = True
    ) -> list[FixedExpense]:
        statement = select(FixedExpenseModel).where(FixedExpenseModel.owner_id == owner_id.value)
        if not include_paused:
            statement = statement.where(FixedExpenseModel.is_paused.is_(False))
        statement = statement.order_by(FixedExpenseModel.title)
        # Settlements come with the root: the relationship is selectin-loaded, so listing
        # commitments for a Period does not fire a query per commitment.
        return self._rehydrate_all(self._session.scalars(statement).all())

    def count_for_category(self, owner_id: OwnerId, category_id: CategoryId) -> int:
        statement = (
            select(func.count())
            .select_from(FixedExpenseModel)
            .where(
                FixedExpenseModel.owner_id == owner_id.value,
                FixedExpenseModel.category_id == category_id.value,
            )
        )
        return int(self._session.scalar(statement) or 0)

    def remove(self, commitment: FixedExpense) -> None:
        self._delete(commitment)


class SqlAlchemyUnitOfMeasurementRepository(TrackingRepository[UnitOfMeasurement]):
    """Units are global — not scoped to an owner — so lookups take no owner_id."""

    mapper = UnitOfMeasurementMapper

    def __init__(self, session: Session) -> None:
        super().__init__(session)

    @classmethod
    def model_type(cls) -> type[UnitOfMeasurementModel]:
        return UnitOfMeasurementModel

    def add(self, unit: UnitOfMeasurement) -> None:
        self._insert(unit)

    def add_all(self, units: list[UnitOfMeasurement]) -> None:
        for unit in units:
            self._insert(unit)

    def get(self, unit_id: UnitId) -> UnitOfMeasurement:
        model = self._session.get(UnitOfMeasurementModel, unit_id.value)
        if model is None:
            raise UnitNotFound("No such unit", unit_id=str(unit_id))
        return self._rehydrate(model)

    def find_by_code(self, code: str) -> UnitOfMeasurement | None:
        model = self._session.scalars(
            select(UnitOfMeasurementModel).where(
                UnitOfMeasurementModel.code == code.strip().lower()
            )
        ).one_or_none()
        return self._rehydrate(model) if model is not None else None

    def list_all(self) -> list[UnitOfMeasurement]:
        statement = select(UnitOfMeasurementModel).order_by(UnitOfMeasurementModel.name)
        return self._rehydrate_all(self._session.scalars(statement).all())

    def count(self) -> int:
        return int(
            self._session.scalar(select(func.count()).select_from(UnitOfMeasurementModel)) or 0
        )

    def remove(self, unit: UnitOfMeasurement) -> None:
        self._delete(unit)


class SqlAlchemyItemRepository(TrackingRepository[Item]):
    mapper = ItemMapper

    def __init__(self, session: Session) -> None:
        super().__init__(session)

    @classmethod
    def model_type(cls) -> type[ItemModel]:
        return ItemModel

    def add(self, item: Item) -> None:
        self._insert(item)

    def get(self, owner_id: OwnerId, item_id: ItemId) -> Item:
        model = self._session.scalars(
            select(ItemModel).where(
                ItemModel.id == item_id.value,
                ItemModel.owner_id == owner_id.value,
            )
        ).one_or_none()
        if model is None:
            raise ItemNotFound("No such item", item_id=str(item_id))
        return self._rehydrate(model)

    def list_for_owner(self, owner_id: OwnerId, *, include_archived: bool = False) -> list[Item]:
        statement = select(ItemModel).where(ItemModel.owner_id == owner_id.value)
        if not include_archived:
            statement = statement.where(ItemModel.is_archived.is_(False))
        statement = statement.order_by(ItemModel.name)
        return self._rehydrate_all(self._session.scalars(statement).all())

    def remove(self, item: Item) -> None:
        self._delete(item)
