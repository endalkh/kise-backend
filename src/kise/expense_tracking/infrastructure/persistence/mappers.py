"""Mappers for the Expense Tracking aggregates.

The interesting one is ``FixedExpenseMapper``: a FixedExpense owns its Settlements, so the mapper
has to synchronise a **collection** — added Settlements become new rows, removed ones become deleted
rows (``delete-orphan`` on the relationship), and corrected ones are updated in place. That work is
what an aggregate boundary costs in a mapped world, and it is contained here rather than smeared
across use cases.
"""

from __future__ import annotations

from kise.expense_tracking.domain.models import (
    Category,
    Expense,
    FixedExpense,
    Item,
    Settlement,
    UnitOfMeasurement,
)
from kise.expense_tracking.domain.value_objects import Color, PaymentMethod, Quantity
from kise.expense_tracking.infrastructure.persistence.models import (
    CategoryModel,
    ExpenseModel,
    FixedExpenseModel,
    ItemModel,
    SettlementModel,
    UnitOfMeasurementModel,
)
from kise.shared_kernel.domain.calendar.calendar_kind import CalendarKind
from kise.shared_kernel.domain.calendar.period import Period
from kise.shared_kernel.domain.calendar.spend_date import SpendDate
from kise.shared_kernel.domain.identifiers import (
    CategoryId,
    ExpenseId,
    FixedExpenseId,
    ItemId,
    OwnerId,
    SettlementId,
    UnitId,
)
from kise.shared_kernel.infrastructure.mapper import (
    money_from_columns,
    money_to_columns,
)


class CategoryMapper:
    @staticmethod
    def to_model(category: Category) -> CategoryModel:
        return CategoryModel(
            id=category.id.value,
            owner_id=category.owner_id.value,
            name=category.name,
            name_key=category.comparison_key,
            name_am=category.name_am,
            color=category.color.value,
            icon=category.icon,
            is_archived=category.is_archived,
            is_default=category.is_default,
        )

    @staticmethod
    def to_domain(entity: CategoryModel) -> Category:
        return Category(
            CategoryId(entity.id),
            owner_id=OwnerId(entity.owner_id),
            name=entity.name,
            name_am=entity.name_am,
            color=Color(entity.color),
            icon=entity.icon,
            is_archived=entity.is_archived,
            is_default=entity.is_default,
        )

    @staticmethod
    def update_model(entity: CategoryModel, category: Category) -> None:
        entity.name = category.name
        entity.name_key = category.comparison_key
        entity.name_am = category.name_am
        entity.color = category.color.value
        entity.icon = category.icon
        entity.is_archived = category.is_archived


class ExpenseMapper:
    @staticmethod
    def to_model(expense: Expense) -> ExpenseModel:
        amount_minor, currency = money_to_columns(expense.amount)
        return ExpenseModel(
            id=expense.id.value,
            owner_id=expense.owner_id.value,
            category_id=expense.category_id.value,
            amount_minor=amount_minor,
            currency=currency,
            spent_on=expense.spent_on.gregorian,
            entered_in=expense.spent_on.entered_in.value,
            note=expense.note,
            payment_method=expense.payment_method.value,
            item_id=expense.item_id.value if expense.item_id else None,
            quantity_milli=expense.quantity.milli if expense.quantity else None,
            unit_id=expense.unit_id.value if expense.unit_id else None,
        )

    @staticmethod
    def to_domain(entity: ExpenseModel) -> Expense:
        return Expense(
            ExpenseId(entity.id),
            owner_id=OwnerId(entity.owner_id),
            category_id=CategoryId(entity.category_id),
            amount=money_from_columns(entity.amount_minor, entity.currency),
            spent_on=SpendDate(entity.spent_on, CalendarKind.parse(entity.entered_in)),
            note=entity.note,
            payment_method=PaymentMethod.parse(entity.payment_method),
            item_id=ItemId(entity.item_id) if entity.item_id else None,
            quantity=Quantity(entity.quantity_milli) if entity.quantity_milli is not None else None,
            unit_id=UnitId(entity.unit_id) if entity.unit_id else None,
        )

    @staticmethod
    def update_model(entity: ExpenseModel, expense: Expense) -> None:
        entity.amount_minor, entity.currency = money_to_columns(expense.amount)
        entity.category_id = expense.category_id.value
        entity.spent_on = expense.spent_on.gregorian
        entity.entered_in = expense.spent_on.entered_in.value
        entity.note = expense.note
        entity.payment_method = expense.payment_method.value
        entity.item_id = expense.item_id.value if expense.item_id else None
        entity.quantity_milli = expense.quantity.milli if expense.quantity else None
        entity.unit_id = expense.unit_id.value if expense.unit_id else None


class SettlementMapper:
    """Child entity of FixedExpense; never mapped on its own from a repository."""

    @staticmethod
    def to_model(settlement: Settlement, *, owner_id: OwnerId) -> SettlementModel:
        amount_minor, currency = money_to_columns(settlement.amount)
        return SettlementModel(
            id=settlement.id.value,
            owner_id=owner_id.value,
            period_year=settlement.period.year,
            period_month=settlement.period.month,
            amount_minor=amount_minor,
            currency=currency,
            settled_on=settlement.settled_on,
        )

    @staticmethod
    def to_domain(entity: SettlementModel, *, anchor_calendar: CalendarKind) -> Settlement:
        # The calendar comes from the parent commitment: a Settlement is always in the Anchor
        # Calendar, so it is not stored twice.
        return Settlement(
            SettlementId(entity.id),
            period=Period(anchor_calendar, entity.period_year, entity.period_month),
            amount=money_from_columns(entity.amount_minor, entity.currency),
            settled_on=entity.settled_on,
        )

    @staticmethod
    def update_model(entity: SettlementModel, settlement: Settlement) -> None:
        entity.amount_minor, entity.currency = money_to_columns(settlement.amount)
        entity.settled_on = settlement.settled_on


class FixedExpenseMapper:
    @staticmethod
    def to_model(commitment: FixedExpense) -> FixedExpenseModel:
        amount_minor, currency = money_to_columns(commitment.amount)
        entity = FixedExpenseModel(
            id=commitment.id.value,
            owner_id=commitment.owner_id.value,
            category_id=commitment.category_id.value,
            title=commitment.title,
            amount_minor=amount_minor,
            currency=currency,
            anchor_calendar=commitment.anchor_calendar.value,
            start_year=commitment.start_period.year,
            start_month=commitment.start_period.month,
            end_year=commitment.end_period.year if commitment.end_period else None,
            end_month=commitment.end_period.month if commitment.end_period else None,
            due_day=commitment.due_day.value,
            note=commitment.note,
            is_paused=commitment.is_paused,
        )
        entity.settlements = [
            SettlementMapper.to_model(settlement, owner_id=commitment.owner_id)
            for settlement in commitment.settlements
        ]
        return entity

    @staticmethod
    def to_domain(entity: FixedExpenseModel) -> FixedExpense:
        anchor = CalendarKind.parse(entity.anchor_calendar)
        end_period = (
            Period(anchor, entity.end_year, entity.end_month)
            if entity.end_year is not None and entity.end_month is not None
            else None
        )
        return FixedExpense(
            FixedExpenseId(entity.id),
            owner_id=OwnerId(entity.owner_id),
            category_id=CategoryId(entity.category_id),
            title=entity.title,
            amount=money_from_columns(entity.amount_minor, entity.currency),
            start_period=Period(anchor, entity.start_year, entity.start_month),
            end_period=end_period,
            due_day=entity.due_day,
            note=entity.note,
            is_paused=entity.is_paused,
            settlements=[
                SettlementMapper.to_domain(child, anchor_calendar=anchor)
                for child in entity.settlements
            ],
        )

    @staticmethod
    def update_model(entity: FixedExpenseModel, commitment: FixedExpense) -> None:
        entity.amount_minor, entity.currency = money_to_columns(commitment.amount)
        entity.category_id = commitment.category_id.value
        entity.title = commitment.title
        entity.anchor_calendar = commitment.anchor_calendar.value
        entity.start_year = commitment.start_period.year
        entity.start_month = commitment.start_period.month
        entity.end_year = commitment.end_period.year if commitment.end_period else None
        entity.end_month = commitment.end_period.month if commitment.end_period else None
        entity.due_day = commitment.due_day.value
        entity.note = commitment.note
        entity.is_paused = commitment.is_paused
        FixedExpenseMapper._sync_settlements(entity, commitment)

    @staticmethod
    def _sync_settlements(entity: FixedExpenseModel, commitment: FixedExpense) -> None:
        """Bring the child rows in line with the aggregate's Settlements.

        Added -> inserted, removed -> deleted by ``delete-orphan``, corrected -> updated.
        """
        existing = {child.id: child for child in entity.settlements}
        wanted = {settlement.id.value: settlement for settlement in commitment.settlements}

        for settlement_id, settlement in wanted.items():
            child = existing.get(settlement_id)
            if child is None:
                entity.settlements.append(
                    SettlementMapper.to_model(settlement, owner_id=commitment.owner_id)
                )
            else:
                SettlementMapper.update_model(child, settlement)

        for settlement_id, child in existing.items():
            if settlement_id not in wanted:
                entity.settlements.remove(child)


class UnitOfMeasurementMapper:
    @staticmethod
    def to_model(unit: UnitOfMeasurement) -> UnitOfMeasurementModel:
        return UnitOfMeasurementModel(
            id=unit.id.value,
            code=unit.code,
            name=unit.name,
            name_am=unit.name_am,
            is_system=unit.is_system,
        )

    @staticmethod
    def to_domain(entity: UnitOfMeasurementModel) -> UnitOfMeasurement:
        return UnitOfMeasurement(
            UnitId(entity.id),
            code=entity.code,
            name=entity.name,
            name_am=entity.name_am,
            is_system=entity.is_system,
        )

    @staticmethod
    def update_model(entity: UnitOfMeasurementModel, unit: UnitOfMeasurement) -> None:
        entity.name = unit.name
        entity.name_am = unit.name_am


class ItemMapper:
    @staticmethod
    def to_model(item: Item) -> ItemModel:
        return ItemModel(
            id=item.id.value,
            owner_id=item.owner_id.value,
            name=item.name,
            name_key=item.comparison_key,
            name_am=item.name_am,
            default_unit_id=item.default_unit_id.value if item.default_unit_id else None,
            is_archived=item.is_archived,
        )

    @staticmethod
    def to_domain(entity: ItemModel) -> Item:
        return Item(
            ItemId(entity.id),
            owner_id=OwnerId(entity.owner_id),
            name=entity.name,
            name_am=entity.name_am,
            default_unit_id=UnitId(entity.default_unit_id) if entity.default_unit_id else None,
            is_archived=entity.is_archived,
        )

    @staticmethod
    def update_model(entity: ItemModel, item: Item) -> None:
        entity.name = item.name
        entity.name_key = item.comparison_key
        entity.name_am = item.name_am
        entity.default_unit_id = item.default_unit_id.value if item.default_unit_id else None
        entity.is_archived = item.is_archived
