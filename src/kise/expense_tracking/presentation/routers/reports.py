"""The reporting router: the month-end item-usage report.

``GET /api/reports/item-usage?period_year=2018&period_month=11&period_calendar=ethiopian`` returns,
for that month, how much of each item was bought in each unit — the "12 kg of sugar" view — with the
money spent and a shape the app charts. The period is resolved server-side to its Gregorian span, so
an Ethiopian month like ሐምሌ 2018 works without the client doing calendar arithmetic.
"""

from __future__ import annotations

from fastapi import APIRouter, Query

from kise.expense_tracking.application.commands import ItemUsageQuery, PeriodInput
from kise.expense_tracking.presentation.routers.catalog_schemas import ItemUsageReportResponse
from kise.platform.api.dependencies import CurrentOwner, ServicesDep

router = APIRouter(prefix="/api/reports", tags=["reports"])


@router.get("/item-usage", response_model=ItemUsageReportResponse)
def item_usage(
    owner: CurrentOwner,
    services: ServicesDep,
    period_year: int = Query(ge=1),
    period_month: int = Query(ge=1, le=13),
    period_calendar: str = Query(default="ethiopian"),
) -> ItemUsageReportResponse:
    query = ItemUsageQuery(
        owner_id=owner.owner_id,
        period=PeriodInput(
            year=period_year, month=period_month, calendar=period_calendar
        ),
    )
    return ItemUsageReportResponse.of(services.item_usage.for_period(query))
