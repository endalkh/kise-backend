"""The expenses router: list, record, get, update, delete.

Listing is the interesting one. The same endpoint answers "this month" and "between these two
dates", in either calendar, because the query carries the calendar with each value:

* ``period_year`` + ``period_month`` (+ ``period_calendar``, default Ethiopian) list one month,
  resolved server-side to its Gregorian span — so ``ሐምሌ 2018`` becomes 8 Jul – 6 Aug without the
  client doing calendar arithmetic.
* ``since`` / ``until`` (each with its own calendar) list an explicit range.
* ``category_id`` (repeatable) narrows to specific categories.

A ``Period`` wins over loose dates, matching ``ExpenseService.list``. Amounts and dates come back in
the dual-calendar / minor-units wire format the whole API uses.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Query, Response, status

from kise.expense_tracking.application.commands import (
    DateInput,
    ListExpensesQuery,
    PeriodInput,
)
from kise.expense_tracking.presentation.schemas import (
    ExpensePageResponse,
    ExpenseResponse,
    RecordExpenseRequest,
    UpdateExpenseRequest,
)
from kise.platform.api.dependencies import CurrentOwner, ServicesDep
from kise.shared_kernel.domain.identifiers import CategoryId, ExpenseId

router = APIRouter(prefix="/api/expenses", tags=["expenses"])


@router.get("", response_model=ExpensePageResponse)
def list_expenses(
    owner: CurrentOwner,
    services: ServicesDep,
    since: str | None = Query(default=None, description="Start date, inclusive"),
    until: str | None = Query(default=None, description="End date, inclusive"),
    date_calendar: str = Query(
        default="gregorian", description="Calendar for since/until"
    ),
    period_year: int | None = Query(default=None, ge=1),
    period_month: int | None = Query(default=None, ge=1, le=13),
    period_calendar: str = Query(default="ethiopian"),
    category_id: Annotated[list[str] | None, Query()] = None,
    limit: int = Query(default=50, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
) -> ExpensePageResponse:
    period = (
        PeriodInput(year=period_year, month=period_month, calendar=period_calendar)
        if period_year is not None and period_month is not None
        else None
    )
    query = ListExpensesQuery(
        owner_id=owner.owner_id,
        since=DateInput(value=since, calendar=date_calendar) if since else None,
        until=DateInput(value=until, calendar=date_calendar) if until else None,
        period=period,
        category_ids=tuple(CategoryId.parse(cid) for cid in (category_id or ())),
        limit=limit,
        offset=offset,
    )
    return ExpensePageResponse.of(services.expenses.list(query))


@router.post("", response_model=ExpenseResponse, status_code=status.HTTP_201_CREATED)
def record_expense(
    request: RecordExpenseRequest, owner: CurrentOwner, services: ServicesDep
) -> ExpenseResponse:
    view = services.expenses.record(request.to_command(owner.owner_id))
    return ExpenseResponse.of(view)


@router.get("/{expense_id}", response_model=ExpenseResponse)
def get_expense(
    expense_id: str, owner: CurrentOwner, services: ServicesDep
) -> ExpenseResponse:
    view = services.expenses.get(owner.owner_id, ExpenseId.parse(expense_id))
    return ExpenseResponse.of(view)


@router.patch("/{expense_id}", response_model=ExpenseResponse)
def update_expense(
    expense_id: str,
    request: UpdateExpenseRequest,
    owner: CurrentOwner,
    services: ServicesDep,
) -> ExpenseResponse:
    command = request.to_command(owner.owner_id, ExpenseId.parse(expense_id))
    view = services.expenses.update(command)
    return ExpenseResponse.of(view)


@router.delete("/{expense_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_expense(
    expense_id: str, owner: CurrentOwner, services: ServicesDep
) -> Response:
    services.expenses.delete(owner.owner_id, ExpenseId.parse(expense_id))
    return Response(status_code=status.HTTP_204_NO_CONTENT)
