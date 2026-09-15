"""The units-of-measurement router.

Units are global and seedable, and admins can add more — so listing needs auth (you must be signed
in) but is not owner-scoped, and creating adds to the shared set. There is no delete: a unit that an
expense was recorded against must never dangle, and the seeded system units are permanent.
"""

from __future__ import annotations

from fastapi import APIRouter, status

from kise.expense_tracking.presentation.routers.catalog_schemas import (
    CreateUnitRequest,
    UnitResponse,
)
from kise.platform.api.dependencies import CurrentOwner, ServicesDep

router = APIRouter(prefix="/api/units", tags=["units"])


@router.get("", response_model=list[UnitResponse])
def list_units(_: CurrentOwner, services: ServicesDep) -> list[UnitResponse]:
    return [UnitResponse.of(view) for view in services.units.list()]


@router.post("", response_model=UnitResponse, status_code=status.HTTP_201_CREATED)
def create_unit(
    request: CreateUnitRequest, _: CurrentOwner, services: ServicesDep
) -> UnitResponse:
    """Add a custom unit. The code must be unique across the whole install."""
    return UnitResponse.of(services.units.create(request.to_command()))
