"""Policies — rules that are real, but do not belong to any single aggregate.

An aggregate can only guarantee what it can see. "No two Categories of the same Owner share a name"
spans every Category the Owner has, and "this Category belongs to me" spans two aggregates. Hiding
such rules inside an aggregate would be a lie, so they live here as named, testable policies that
use cases invoke explicitly.
"""

from __future__ import annotations

from collections.abc import Iterable

from kise.expense_tracking.domain.errors import CategoryArchived, CategoryNameTaken, NotOwned
from kise.expense_tracking.domain.models import Category
from kise.shared_kernel.domain.identifiers import CategoryId, OwnerId


def ensure_name_is_free(
    name: str,
    *,
    existing: Iterable[Category] | Iterable[str],
    ignoring: CategoryId | None = None,
) -> None:
    """Category names are unique per Owner, case-insensitively (FR-3.4).

    ``ignoring`` lets a rename skip the category being renamed.
    """
    wanted = " ".join(str(name).split()).casefold()
    for item in existing:
        if isinstance(item, Category):
            if ignoring is not None and item.id == ignoring:
                continue
            taken = item.comparison_key
        else:
            taken = " ".join(str(item).split()).casefold()
        if taken == wanted:
            raise CategoryNameTaken(name)


def ensure_owned_by(owner_id: OwnerId, *records: object) -> None:
    """Every record touched by a use case must belong to the calling Owner (FR-1.4).

    Repositories are Owner-scoped, so this is a second line of defence rather than the only one —
    but it is the line that turns a mistake into a refusal instead of a data leak.
    """
    for record in records:
        record_owner = getattr(record, "owner_id", None)
        if record_owner is None:
            raise NotOwned(type(record).__name__.lower())
        if record_owner != owner_id:
            raise NotOwned(type(record).__name__.lower())


def ensure_category_usable(category: Category) -> None:
    """New spending may only be filed under a live Category; archived ones are history only."""
    if category.is_archived:
        raise CategoryArchived(
            f"{category.name!r} is archived, so new expenses cannot use it",
            category=category.name,
        )
