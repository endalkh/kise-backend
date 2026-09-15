"""The Category aggregate — the bucket an Expense belongs to.

Categories are archived, never deleted, once expenses point at them: a report of last ሐምሌ has to
stay readable. Archiving is a state on the aggregate, so an archived Category still explains old
records but disappears from pickers.
"""

from __future__ import annotations

from kise.expense_tracking.domain.errors import CategoryArchived
from kise.expense_tracking.domain.value_objects.values import (
    MAX_CATEGORY_NAME_LENGTH,
    MAX_ICON_LENGTH,
    Color,
    clean_optional_text,
    clean_required_text,
)
from kise.shared_kernel.domain.entity import AggregateRoot
from kise.shared_kernel.domain.identifiers import CategoryId, OwnerId


class Category(AggregateRoot):
    """A spending bucket belonging to one Owner."""

    def __init__(
        self,
        category_id: CategoryId,
        *,
        owner_id: OwnerId,
        name: str,
        name_am: str | None = None,
        color: Color | None = None,
        icon: str | None = None,
        is_archived: bool = False,
        is_default: bool = False,
    ) -> None:
        super().__init__(category_id)
        self._owner_id = owner_id
        self._name = clean_required_text(
            name, field="name", max_length=MAX_CATEGORY_NAME_LENGTH
        )
        self._name_am = clean_optional_text(
            name_am, field="name_am", max_length=MAX_CATEGORY_NAME_LENGTH
        )
        self._color = color or Color()
        self._icon = clean_optional_text(icon, field="icon", max_length=MAX_ICON_LENGTH)
        self._is_archived = is_archived
        self._is_default = is_default

    @classmethod
    def create(
        cls,
        *,
        owner_id: OwnerId,
        name: str,
        name_am: str | None = None,
        color: Color | str | None = None,
        icon: str | None = None,
        is_default: bool = False,
        category_id: CategoryId | None = None,
    ) -> Category:
        return cls(
            category_id or CategoryId.new(),
            owner_id=owner_id,
            name=name,
            name_am=name_am,
            color=Color(color) if isinstance(color, str) else color,
            icon=icon,
            is_default=is_default,
        )

    # -- state ----------------------------------------------------------
    @property
    def id(self) -> CategoryId:
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
    def color(self) -> Color:
        return self._color

    @property
    def icon(self) -> str | None:
        return self._icon

    @property
    def is_archived(self) -> bool:
        return self._is_archived

    @property
    def is_default(self) -> bool:
        """Seeded on registration. Defaults may be archived but are never name-locked."""
        return self._is_default

    def label(self, language: str = "am") -> str:
        """The Amharic name when there is one and Amharic is asked for, else the name."""
        if language == "am" and self._name_am:
            return self._name_am
        return self._name

    @property
    def comparison_key(self) -> str:
        """Case-insensitive key used for the per-Owner uniqueness policy."""
        return self._name.casefold()

    # -- behaviour ------------------------------------------------------
    def _guard_not_archived(self, action: str) -> None:
        if self._is_archived:
            raise CategoryArchived(
                f"Cannot {action} {self._name!r} because it is archived; restore it first",
                category=self._name,
            )

    def rename(self, name: str, name_am: str | None = None) -> None:
        self._guard_not_archived("rename")
        self._name = clean_required_text(name, field="name", max_length=MAX_CATEGORY_NAME_LENGTH)
        if name_am is not None:
            self._name_am = clean_optional_text(
                name_am, field="name_am", max_length=MAX_CATEGORY_NAME_LENGTH
            )

    def recolor(self, color: Color | str) -> None:
        self._guard_not_archived("recolour")
        self._color = Color(color) if isinstance(color, str) else color

    def set_icon(self, icon: str | None) -> None:
        self._guard_not_archived("change the icon of")
        self._icon = clean_optional_text(icon, field="icon", max_length=MAX_ICON_LENGTH)

    def archive(self) -> None:
        if self._is_archived:
            raise CategoryArchived(f"{self._name!r} is already archived", category=self._name)
        self._is_archived = True

    def restore(self) -> None:
        self._is_archived = False


#: The categories every new Owner starts with (FR-3.1): (english, amharic, colour, icon).
DEFAULT_CATEGORIES: tuple[tuple[str, str, str, str], ...] = (
    ("Food", "ምግብ", "#E53935", "restaurant"),
    ("Transport", "ትራንስፖርት", "#1E88E5", "directions_bus"),
    ("Rent", "ቤት ኪራይ", "#6D4C41", "home"),
    ("Utilities", "መብራትና ውሃ", "#FB8C00", "bolt"),
    ("Health", "ጤና", "#43A047", "local_hospital"),
    ("Education", "ትምህርት", "#3949AB", "school"),
    ("Airtime & Internet", "ካርድና ኢንተርኔት", "#00897B", "wifi"),
    ("Clothing", "ልብስ", "#8E24AA", "checkroom"),
    ("Savings", "ቁጠባ", "#00ACC1", "savings"),
    ("Other", "ሌላ", "#607D8B", "more_horiz"),
)


def default_categories_for(owner_id: OwnerId) -> list[Category]:
    """Build the starter set. Used by the ``OwnerRegistered`` subscriber."""
    return [
        Category.create(
            owner_id=owner_id, name=name, name_am=name_am, color=color, icon=icon, is_default=True
        )
        for name, name_am, color, icon in DEFAULT_CATEGORIES
    ]
