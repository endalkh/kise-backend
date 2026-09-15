"""The Item aggregate — a thing the Owner buys, tracked across expenses.

"Sugar", "Cooking oil", "Injera". An expense may point at an Item and say how much of it was
bought, which is what lets the month-end report say "12 kg of sugar" rather than only "480 birr on
groceries".

Items behave like Categories in the ways that matter: owner-scoped, name-unique per Owner
(case-insensitively), and archived rather than deleted once expenses reference them, so history
stays readable. An Item carries an optional **default unit** — the unit it is usually bought in — so
the app can pre-fill the picker, while each expense is still free to override it.
"""

from __future__ import annotations

from kise.expense_tracking.domain.errors import ItemArchived
from kise.expense_tracking.domain.value_objects.values import (
    MAX_CATEGORY_NAME_LENGTH,
    clean_optional_text,
    clean_required_text,
)
from kise.shared_kernel.domain.entity import AggregateRoot
from kise.shared_kernel.domain.identifiers import ItemId, OwnerId, UnitId

MAX_ITEM_NAME_LENGTH = MAX_CATEGORY_NAME_LENGTH


class Item(AggregateRoot):
    """Something bought, belonging to one Owner."""

    def __init__(
        self,
        item_id: ItemId,
        *,
        owner_id: OwnerId,
        name: str,
        name_am: str | None = None,
        default_unit_id: UnitId | None = None,
        is_archived: bool = False,
    ) -> None:
        super().__init__(item_id)
        self._owner_id = owner_id
        self._name = clean_required_text(name, field="name", max_length=MAX_ITEM_NAME_LENGTH)
        self._name_am = clean_optional_text(
            name_am, field="name_am", max_length=MAX_ITEM_NAME_LENGTH
        )
        self._default_unit_id = default_unit_id
        self._is_archived = is_archived

    @classmethod
    def create(
        cls,
        *,
        owner_id: OwnerId,
        name: str,
        name_am: str | None = None,
        default_unit_id: UnitId | None = None,
        item_id: ItemId | None = None,
    ) -> Item:
        return cls(
            item_id or ItemId.new(),
            owner_id=owner_id,
            name=name,
            name_am=name_am,
            default_unit_id=default_unit_id,
        )

    # -- state ----------------------------------------------------------
    @property
    def id(self) -> ItemId:
        return self._id  # type: ignore[return-value]

    @property
    def owner_id(self) -> OwnerId:
        return self._owner_id

    @property
    def name(self) -> str:
        return self._name

    @property
    def name_am(self) -> str | None:
        return self._name_am

    @property
    def default_unit_id(self) -> UnitId | None:
        return self._default_unit_id

    @property
    def is_archived(self) -> bool:
        return self._is_archived

    @property
    def comparison_key(self) -> str:
        """Case-insensitive key for the per-Owner uniqueness policy."""
        return self._name.casefold()

    def label(self, language: str = "am") -> str:
        if language == "am" and self._name_am:
            return self._name_am
        return self._name

    # -- behaviour ------------------------------------------------------
    def _guard_not_archived(self, action: str) -> None:
        if self._is_archived:
            raise ItemArchived(
                f"Cannot {action} {self._name!r} because it is archived; restore it first",
                item=self._name,
            )

    def rename(self, name: str, name_am: str | None = None) -> None:
        self._guard_not_archived("rename")
        self._name = clean_required_text(name, field="name", max_length=MAX_ITEM_NAME_LENGTH)
        if name_am is not None:
            self._name_am = clean_optional_text(
                name_am, field="name_am", max_length=MAX_ITEM_NAME_LENGTH
            )

    def set_default_unit(self, unit_id: UnitId | None) -> None:
        self._guard_not_archived("change the default unit of")
        self._default_unit_id = unit_id

    def archive(self) -> None:
        if self._is_archived:
            raise ItemArchived(f"{self._name!r} is already archived", item=self._name)
        self._is_archived = True

    def restore(self) -> None:
        self._is_archived = False
