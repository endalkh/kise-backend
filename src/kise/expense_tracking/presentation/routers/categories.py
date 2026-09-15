"""The categories router: list, create, update, and the archive-or-delete removal.

The one endpoint worth reading is DELETE. A category with expenses attached is *archived*, never
deleted, so past reports stay readable. The service says which happened by its return value — the
archived view, or ``None`` when it was really deleted — and this router turns that into either a
``200`` with the archived category or a ``204 No Content``. The client can tell the difference and
say "archived, because 12 expenses use it" instead of pretending it vanished.
"""

from __future__ import annotations

from fastapi import APIRouter, Query, Response, status

from kise.expense_tracking.presentation.schemas import (
    CategoryResponse,
    CreateCategoryRequest,
    UpdateCategoryRequest,
)
from kise.platform.api.dependencies import CurrentOwner, ServicesDep
from kise.shared_kernel.domain.identifiers import CategoryId

router = APIRouter(prefix="/api/categories", tags=["categories"])


@router.get("", response_model=list[CategoryResponse])
def list_categories(
    owner: CurrentOwner,
    services: ServicesDep,
    include_archived: bool = Query(default=False),
) -> list[CategoryResponse]:
    views = services.categories.list(owner.owner_id, include_archived=include_archived)
    return [CategoryResponse.of(view) for view in views]


@router.post("", response_model=CategoryResponse, status_code=status.HTTP_201_CREATED)
def create_category(
    request: CreateCategoryRequest, owner: CurrentOwner, services: ServicesDep
) -> CategoryResponse:
    view = services.categories.create(request.to_command(owner.owner_id))
    return CategoryResponse.of(view)


@router.patch("/{category_id}", response_model=CategoryResponse)
def update_category(
    category_id: str,
    request: UpdateCategoryRequest,
    owner: CurrentOwner,
    services: ServicesDep,
) -> CategoryResponse:
    command = request.to_command(owner.owner_id, CategoryId.parse(category_id))
    view = services.categories.update(command)
    return CategoryResponse.of(view)


@router.delete(
    "/{category_id}",
    response_model=CategoryResponse,
    responses={status.HTTP_204_NO_CONTENT: {"description": "Deleted; nothing used it"}},
)
def remove_category(
    category_id: str, owner: CurrentOwner, services: ServicesDep
) -> Response | CategoryResponse:
    """Delete when nothing uses it (204), archive when something does (200 + the archived view)."""
    view = services.categories.remove(owner.owner_id, CategoryId.parse(category_id))
    if view is None:
        return Response(status_code=status.HTTP_204_NO_CONTENT)
    return CategoryResponse.of(view)
