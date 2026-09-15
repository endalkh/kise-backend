"""The Dynamic Expense application service.

Every method here resolves dates the same way: the command says which calendar its value is in, this
service turns it into a ``SpendDate``, and the Gregorian value is what gets stored. That one step is
what makes "I spent this on ሐምሌ 15" and "I spent this on 22 July" the same fact.
"""

from __future__ import annotations

from kise.expense_tracking.application.commands import (
    ExpenseFilter,
    ItemLineInput,
    ListExpensesQuery,
    RecordExpenseCommand,
    UpdateExpenseCommand,
)
from kise.expense_tracking.application.services.items import ItemService
from kise.expense_tracking.application.views import (
    ExpensePage,
    ExpenseView,
)
from kise.expense_tracking.domain.models import Category, Expense, Item, Quantity, UnitOfMeasurement
from kise.expense_tracking.domain.policies import ensure_category_usable, ensure_owned_by
from kise.expense_tracking.infrastructure.persistence.repositories import (
    SqlAlchemyCategoryRepository,
    SqlAlchemyExpenseRepository,
    SqlAlchemyItemRepository,
    SqlAlchemyUnitOfMeasurementRepository,
)
from kise.shared_kernel.application.ports import UnitOfWork
from kise.shared_kernel.domain.errors import ValidationError
from kise.shared_kernel.domain.identifiers import CategoryId, ExpenseId, ItemId, OwnerId, UnitId
from kise.shared_kernel.domain.money import Money, sum_money


class ExpenseService:
    def __init__(
        self,
        expenses: SqlAlchemyExpenseRepository,
        categories: SqlAlchemyCategoryRepository,
        uow: UnitOfWork,
        *,
        items: SqlAlchemyItemRepository | None = None,
        units: SqlAlchemyUnitOfMeasurementRepository | None = None,
        currency: str = "ETB",
    ) -> None:
        self._expenses = expenses
        self._categories = categories
        self._uow = uow
        self._items = items
        self._units = units
        self._currency = currency

    # -- item line resolution ------------------------------------------
    def _resolve_item_line(
        self, owner_id: OwnerId, line: ItemLineInput
    ) -> tuple[ItemId, Quantity, UnitId]:
        """Turn the command's item line into (item_id, quantity, unit_id), creating a new item

        by name when needed. Requires items+units repos to be wired (they always are in the app).
        """
        if self._items is None or self._units is None:  # pragma: no cover - always wired
            raise RuntimeError("ExpenseService needs item and unit repositories for item lines")
        if line.unit_id is None:
            raise ValidationError("an item line needs a unit", field="unit_id")
        unit = self._units.get(line.unit_id)  # raises UnitNotFound if bogus
        if line.quantity is None:
            raise ValidationError("an item line needs a quantity", field="quantity")
        quantity = Quantity.of(line.quantity)

        item_service = ItemService(self._items, self._units, self._expenses, self._uow)
        item = item_service.resolve_or_create(
            owner_id,
            item_id=line.item_id,
            item_name=line.item_name,
            item_name_am=line.item_name_am,
            default_unit_id=unit.id,
        )
        ensure_owned_by(owner_id, item)
        return item.id, quantity, unit.id

    def _load_item_and_unit(
        self, owner_id: OwnerId, expense: Expense
    ) -> tuple[Item | None, UnitOfMeasurement | None]:
        item = (
            self._items.get(owner_id, expense.item_id)
            if expense.item_id and self._items
            else None
        )
        unit = (
            self._units.get(expense.unit_id) if expense.unit_id and self._units else None
        )
        return item, unit

    # -- commands -------------------------------------------------------
    def record(self, command: RecordExpenseCommand) -> ExpenseView:
        # Raises CategoryNotFound when it belongs to someone else: the repository is owner-scoped.
        category = self._categories.get(command.owner_id, command.category_id)
        ensure_owned_by(command.owner_id, category)
        ensure_category_usable(category)

        item_id = quantity = unit_id = None
        if command.item is not None and command.item.is_present:
            item_id, quantity, unit_id = self._resolve_item_line(command.owner_id, command.item)

        expense = Expense.record(
            owner_id=command.owner_id,
            category_id=category.id,
            amount=Money(command.amount_minor, self._currency),
            spent_on=command.spent_on.resolve(),
            note=command.note,
            payment_method=command.payment_method,
            item_id=item_id,
            quantity=quantity,
            unit_id=unit_id,
        )
        self._expenses.add(expense)
        self._uow.commit()
        item, unit = self._load_item_and_unit(command.owner_id, expense)
        return ExpenseView.of(expense, category, item, unit)

    def update(self, command: UpdateExpenseCommand) -> ExpenseView:
        expense = self._expenses.get(command.owner_id, command.expense_id)
        ensure_owned_by(command.owner_id, expense)

        category: Category | None = None
        if command.category_id is not None:
            category = self._categories.get(command.owner_id, command.category_id)
            ensure_owned_by(command.owner_id, category)
            ensure_category_usable(category)
            expense.recategorise(category.id)
        if command.amount_minor is not None:
            expense.change_amount(Money(command.amount_minor, self._currency))
        if command.spent_on is not None:
            expense.move_to(command.spent_on.resolve())
        if command.note is not None:
            expense.amend_note(command.note)
        if command.payment_method is not None:
            expense.change_payment_method(command.payment_method)
        if command.clear_item:
            expense.clear_item()
        elif command.item is not None and command.item.is_present:
            item_id, quantity, unit_id = self._resolve_item_line(command.owner_id, command.item)
            expense.set_item(item_id, quantity, unit_id)

        self._uow.commit()
        if category is None:
            category = self._categories.get(command.owner_id, expense.category_id)
        item, unit = self._load_item_and_unit(command.owner_id, expense)
        return ExpenseView.of(expense, category, item, unit)

    def delete(self, owner_id: OwnerId, expense_id: ExpenseId) -> None:
        expense = self._expenses.get(owner_id, expense_id)
        ensure_owned_by(owner_id, expense)
        self._expenses.remove(expense)
        self._uow.commit()

    # -- queries --------------------------------------------------------
    def get(self, owner_id: OwnerId, expense_id: ExpenseId) -> ExpenseView:
        expense = self._expenses.get(owner_id, expense_id)
        category = self._categories.get(owner_id, expense.category_id)
        item, unit = self._load_item_and_unit(owner_id, expense)
        return ExpenseView.of(expense, category, item, unit)

    def list(self, query: ListExpensesQuery) -> ExpensePage:
        """List expenses for a Period or an explicit date range, in either calendar."""
        since = query.since.resolve().gregorian if query.since else None
        until = query.until.resolve().gregorian if query.until else None
        if query.period is not None:
            # A Period wins over loose dates and resolves to its own Gregorian span, which is how
            # "ሐምሌ" becomes 8 July to 6 August without the caller doing arithmetic.
            since, until = query.period.resolve().gregorian_span

        criteria = ExpenseFilter(
            owner_id=query.owner_id,
            since=since,
            until=until,
            category_ids=query.category_ids,
            limit=query.limit,
            offset=query.offset,
        )
        found = self._expenses.list(criteria)
        total = self._expenses.count(criteria)

        by_id: dict[CategoryId, Category] = {
            category.id: category
            for category in self._categories.list_for_owner(
                query.owner_id, include_archived=True
            )
        }
        # Look up items and units once, so a page of expenses does not fire a query per row.
        items_by_id: dict[ItemId, Item] = {}
        if self._items is not None:
            items_by_id = {
                item.id: item
                for item in self._items.list_for_owner(query.owner_id, include_archived=True)
            }
        units_by_id: dict[UnitId, UnitOfMeasurement] = {}
        if self._units is not None:
            units_by_id = {unit.id: unit for unit in self._units.list_all()}

        items = tuple(
            ExpenseView.of(
                expense,
                by_id.get(expense.category_id),
                items_by_id.get(expense.item_id) if expense.item_id else None,
                units_by_id.get(expense.unit_id) if expense.unit_id else None,
            )
            for expense in found
        )
        return ExpensePage(
            items=items,
            total=total,
            limit=criteria.limit,
            offset=criteria.offset,
            # The sum of this page, not of the whole filter: the summary endpoint answers
            # "how much this month".
            total_amount=sum_money([item.amount for item in items], self._currency),
        )
