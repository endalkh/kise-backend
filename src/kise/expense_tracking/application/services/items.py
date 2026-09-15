"""The Item application service.

Items are owner-scoped and behave like Categories: names are unique per Owner (case-insensitively),
and an item referenced by expenses is archived rather than deleted so past reports stay readable.
The one extra concern is the optional **default unit**, validated against the global units table so
an item cannot point at a unit that does not exist.
"""

from __future__ import annotations

from kise.expense_tracking.application.commands import CreateItemCommand
from kise.expense_tracking.application.views import ItemView
from kise.expense_tracking.domain.errors import ItemNameTaken
from kise.expense_tracking.domain.models import Item
from kise.expense_tracking.domain.policies import ensure_owned_by
from kise.expense_tracking.infrastructure.persistence.repositories import (
    SqlAlchemyExpenseRepository,
    SqlAlchemyItemRepository,
    SqlAlchemyUnitOfMeasurementRepository,
)
from kise.shared_kernel.application.ports import UnitOfWork
from kise.shared_kernel.domain.errors import ValidationError
from kise.shared_kernel.domain.identifiers import ItemId, OwnerId, UnitId


class ItemService:
    def __init__(
        self,
        items: SqlAlchemyItemRepository,
        units: SqlAlchemyUnitOfMeasurementRepository,
        expenses: SqlAlchemyExpenseRepository,
        uow: UnitOfWork,
    ) -> None:
        self._items = items
        self._units = units
        self._expenses = expenses
        self._uow = uow

    # -- queries --------------------------------------------------------
    def list(self, owner_id: OwnerId, *, include_archived: bool = False) -> list[ItemView]:
        found = self._items.list_for_owner(owner_id, include_archived=include_archived)
        return [ItemView.of(item) for item in found]

    def get(self, owner_id: OwnerId, item_id: ItemId) -> ItemView:
        return ItemView.of(self._items.get(owner_id, item_id))

    # -- commands -------------------------------------------------------
    def create(self, command: CreateItemCommand) -> ItemView:
        self._ensure_name_free(command.owner_id, command.name)
        if command.default_unit_id is not None:
            self._units.get(command.default_unit_id)  # raises UnitNotFound if bogus
        item = Item.create(
            owner_id=command.owner_id,
            name=command.name,
            name_am=command.name_am,
            default_unit_id=command.default_unit_id,
        )
        self._items.add(item)
        self._uow.commit()
        return ItemView.of(item)

    def archive(self, owner_id: OwnerId, item_id: ItemId) -> ItemView:
        item = self._items.get(owner_id, item_id)
        ensure_owned_by(owner_id, item)
        item.archive()
        self._uow.commit()
        return ItemView.of(item)

    def restore(self, owner_id: OwnerId, item_id: ItemId) -> ItemView:
        item = self._items.get(owner_id, item_id)
        ensure_owned_by(owner_id, item)
        item.restore()
        self._uow.commit()
        return ItemView.of(item)

    def remove(self, owner_id: OwnerId, item_id: ItemId) -> ItemView | None:
        """Delete when nothing uses it, archive when something does (returns the archived view)."""
        item = self._items.get(owner_id, item_id)
        ensure_owned_by(owner_id, item)
        in_use = self._expenses.count_for_item(owner_id, item_id)
        if in_use:
            item.archive()
            self._uow.commit()
            return ItemView.of(item)
        self._items.remove(item)
        self._uow.commit()
        return None

    # -- internals ------------------------------------------------------
    def _ensure_name_free(
        self, owner_id: OwnerId, name: str, *, ignoring: ItemId | None = None
    ) -> None:
        wanted = " ".join(str(name).split()).casefold()
        for existing in self._items.list_for_owner(owner_id, include_archived=True):
            if ignoring is not None and existing.id == ignoring:
                continue
            if existing.comparison_key == wanted:
                raise ItemNameTaken(name)

    def resolve_or_create(
        self,
        owner_id: OwnerId,
        *,
        item_id: ItemId | None,
        item_name: str | None,
        item_name_am: str | None = None,
        default_unit_id: UnitId | None = None,
    ) -> Item:
        """Return the existing item, or create a new one by name — the 'pick or add' behaviour.

        This is what the expense service calls: the user either chose an item from their list or
        typed a new name, and either way we hand back a persisted Item to attach to the expense.
        """
        if item_id is not None:
            return self._items.get(owner_id, item_id)
        if not item_name:
            raise ValidationError(
                "an item line needs either an existing item_id or a new item_name",
                field="item",
            )
        # Reuse an existing item with the same name rather than creating a duplicate.
        wanted = " ".join(str(item_name).split()).casefold()
        for existing in self._items.list_for_owner(owner_id, include_archived=True):
            if existing.comparison_key == wanted:
                return existing
        item = Item.create(
            owner_id=owner_id,
            name=item_name,
            name_am=item_name_am,
            default_unit_id=default_unit_id,
        )
        self._items.add(item)
        return item

    def raw_get(self, owner_id: OwnerId, item_id: ItemId) -> Item:
        """The Item aggregate itself (not a view), for services that need to read its fields."""
        return self._items.get(owner_id, item_id)
