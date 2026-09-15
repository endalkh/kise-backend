"""The Category application service.

Called by the presentation layer, and the only thing that knows the Category repository. Two rules
worth reading before changing anything here:

* **Name uniqueness is checked in this service, not in the aggregate.** It spans every Category the
  Owner has, and an aggregate can only guarantee what it can see. The unique index on
  ``(owner_id, name_key)`` is the backstop.
* **A Category in use is archived, never deleted.** A report of last ሐምሌ has to stay readable, so
  ``remove`` returns the archived Category when it could not delete — the app then says
  "archived, because 12 expenses use it" instead of silently doing the wrong thing.
"""

from __future__ import annotations

from kise.expense_tracking.application.commands import (
    CreateCategoryCommand,
    UpdateCategoryCommand,
)
from kise.expense_tracking.application.views import (
    CategoryView,
)
from kise.expense_tracking.domain.errors import CategoryInUse
from kise.expense_tracking.domain.models import Category
from kise.expense_tracking.domain.policies import ensure_name_is_free, ensure_owned_by
from kise.expense_tracking.infrastructure.persistence.repositories import (
    SqlAlchemyCategoryRepository,
    SqlAlchemyExpenseRepository,
    SqlAlchemyFixedExpenseRepository,
)
from kise.shared_kernel.application.ports import UnitOfWork
from kise.shared_kernel.domain.identifiers import CategoryId, OwnerId


class CategoryService:
    def __init__(
        self,
        categories: SqlAlchemyCategoryRepository,
        expenses: SqlAlchemyExpenseRepository,
        fixed_expenses: SqlAlchemyFixedExpenseRepository,
        uow: UnitOfWork,
    ) -> None:
        self._categories = categories
        self._expenses = expenses
        self._fixed_expenses = fixed_expenses
        self._uow = uow

    # -- queries --------------------------------------------------------
    def list(self, owner_id: OwnerId, *, include_archived: bool = False) -> list[CategoryView]:
        found = self._categories.list_for_owner(owner_id, include_archived=include_archived)
        return [CategoryView.of(category) for category in found]

    def get(self, owner_id: OwnerId, category_id: CategoryId) -> CategoryView:
        return CategoryView.of(self._categories.get(owner_id, category_id))

    # -- commands -------------------------------------------------------
    def create(self, command: CreateCategoryCommand) -> CategoryView:
        existing = self._categories.list_for_owner(command.owner_id, include_archived=True)
        ensure_name_is_free(command.name, existing=existing)

        category = Category.create(
            owner_id=command.owner_id,
            name=command.name,
            name_am=command.name_am,
            color=command.color,
            icon=command.icon,
        )
        self._categories.add(category)
        self._uow.commit()
        return CategoryView.of(category)

    def update(self, command: UpdateCategoryCommand) -> CategoryView:
        category = self._categories.get(command.owner_id, command.category_id)
        ensure_owned_by(command.owner_id, category)

        if command.name is not None:
            existing = self._categories.list_for_owner(command.owner_id, include_archived=True)
            ensure_name_is_free(command.name, existing=existing, ignoring=category.id)
            category.rename(command.name, command.name_am)
        elif command.name_am is not None:
            category.rename(category.name, command.name_am)
        if command.color is not None:
            category.recolor(command.color)
        if command.icon is not None:
            category.set_icon(command.icon)

        self._uow.commit()
        return CategoryView.of(category)

    def archive(self, owner_id: OwnerId, category_id: CategoryId) -> CategoryView:
        category = self._categories.get(owner_id, category_id)
        ensure_owned_by(owner_id, category)
        category.archive()
        self._uow.commit()
        return CategoryView.of(category)

    def restore(self, owner_id: OwnerId, category_id: CategoryId) -> CategoryView:
        category = self._categories.get(owner_id, category_id)
        ensure_owned_by(owner_id, category)
        category.restore()
        self._uow.commit()
        return CategoryView.of(category)

    def remove(
        self, owner_id: OwnerId, category_id: CategoryId, *, archive_when_in_use: bool = True
    ) -> CategoryView | None:
        """Delete when nothing uses it, archive when something does.

        Returns the archived Category, or ``None`` when it was really deleted.
        """
        category = self._categories.get(owner_id, category_id)
        ensure_owned_by(owner_id, category)

        in_use = self._expenses.count_for_category(
            owner_id, category_id
        ) + self._fixed_expenses.count_for_category(owner_id, category_id)

        if in_use:
            if not archive_when_in_use:
                raise CategoryInUse(in_use)
            category.archive()
            self._uow.commit()
            return CategoryView.of(category)

        self._categories.remove(category)
        self._uow.commit()
        return None
