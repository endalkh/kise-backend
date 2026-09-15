"""The items router: list, create, get, and the archive-or-delete removal.

Items are the things the Owner buys. They are picked (or created on the fly) when recording an
expense, so the app lists them for a picker and can add one directly here too. Removal mirrors
categories: an item used by expenses is archived (200 + the archived view), an unused one is deleted
(204).
"""

from __future__ import annotations

from fastapi import APIRouter, Query, Response, status

from kise.expense_tracking.presentation.routers.catalog_schemas import (
    CreateItemRequest,
    ItemResponse,
)
from kise.platform.api.dependencies import CurrentOwner, ServicesDep
from kise.shared_kernel.domain.identifiers import ItemId

router = APIRouter(prefix="/api/items", tags=["items"])


@router.get("", response_model=list[ItemResponse])
def list_items(
    owner: CurrentOwner,
    services: ServicesDep,
    include_archived: bool = Query(default=False),
) -> list[ItemResponse]:
    views = services.items.list(owner.owner_id, include_archived=include_archived)
    return [ItemResponse.of(view) for view in views]


@router.post("", response_model=ItemResponse, status_code=status.HTTP_201_CREATED)
def create_item(
    request: CreateItemRequest, owner: CurrentOwner, services: ServicesDep
) -> ItemResponse:
    return ItemResponse.of(services.items.create(request.to_command(owner.owner_id)))


@router.get("/{item_id}", response_model=ItemResponse)
def get_item(item_id: str, owner: CurrentOwner, services: ServicesDep) -> ItemResponse:
    return ItemResponse.of(services.items.get(owner.owner_id, ItemId.parse(item_id)))


@router.delete(
    "/{item_id}",
    response_model=ItemResponse,
    responses={status.HTTP_204_NO_CONTENT: {"description": "Deleted; nothing used it"}},
)
def remove_item(
    item_id: str, owner: CurrentOwner, services: ServicesDep
) -> Response | ItemResponse:
    view = services.items.remove(owner.owner_id, ItemId.parse(item_id))
    if view is None:
        return Response(status_code=status.HTTP_204_NO_CONTENT)
    return ItemResponse.of(view)
