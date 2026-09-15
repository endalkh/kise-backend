"""Wire schemas for units of measurement, items, and the month-end item-usage report.

Money stays ``{amount_minor, currency}``; quantity goes out both as a tidy decimal string and as
integer thousandths (``quantity_milli``) so the client can do exact arithmetic and the chart can use
the raw number. As everywhere in presentation, Pydantic stops here — requests become commands,
views become responses.
"""

from __future__ import annotations

from pydantic import BaseModel, Field

from kise.expense_tracking.application.commands import (
    CreateItemCommand,
    CreateUnitCommand,
)
from kise.expense_tracking.application.views import (
    ItemUsageReport,
    ItemView,
    UnitView,
)
from kise.expense_tracking.presentation.schemas import MoneyView
from kise.shared_kernel.domain.identifiers import OwnerId, UnitId

# -- units --------------------------------------------------------------


class CreateUnitRequest(BaseModel):
    code: str = Field(min_length=1, max_length=16, examples=["crate", "quintal"])
    name: str = Field(min_length=1, max_length=40)
    name_am: str | None = Field(default=None, max_length=40)

    def to_command(self) -> CreateUnitCommand:
        return CreateUnitCommand(code=self.code, name=self.name, name_am=self.name_am)


class UnitResponse(BaseModel):
    id: str
    code: str
    name: str
    name_am: str | None
    is_system: bool

    @classmethod
    def of(cls, view: UnitView) -> UnitResponse:
        return cls(
            id=str(view.unit_id),
            code=view.code,
            name=view.name,
            name_am=view.name_am,
            is_system=view.is_system,
        )


# -- items --------------------------------------------------------------


class CreateItemRequest(BaseModel):
    name: str = Field(min_length=1, max_length=60)
    name_am: str | None = Field(default=None, max_length=60)
    default_unit_id: str | None = None

    def to_command(self, owner_id: OwnerId) -> CreateItemCommand:
        return CreateItemCommand(
            owner_id=owner_id,
            name=self.name,
            name_am=self.name_am,
            default_unit_id=(
                UnitId.parse(self.default_unit_id) if self.default_unit_id else None
            ),
        )


class ItemResponse(BaseModel):
    id: str
    name: str
    name_am: str | None
    default_unit_id: str | None
    is_archived: bool

    @classmethod
    def of(cls, view: ItemView) -> ItemResponse:
        return cls(
            id=str(view.item_id),
            name=view.name,
            name_am=view.name_am,
            default_unit_id=str(view.default_unit_id) if view.default_unit_id else None,
            is_archived=view.is_archived,
        )


# -- item-usage report --------------------------------------------------


class ItemUsageLineResponse(BaseModel):
    item_id: str
    item_name: str
    item_name_am: str | None
    unit_id: str
    unit_code: str
    unit_name: str
    unit_name_am: str | None
    total_quantity: str  # decimal string, e.g. "15"
    total_quantity_milli: int  # integer thousandths, for the chart
    total_amount: MoneyView
    entry_count: int


class ItemUsageReportResponse(BaseModel):
    period: dict[str, str]  # Period.labels(): dual-calendar labels + span
    currency: str
    lines: list[ItemUsageLineResponse]

    @classmethod
    def of(cls, report: ItemUsageReport) -> ItemUsageReportResponse:
        return cls(
            period=report.period.labels(),
            currency=report.currency,
            lines=[
                ItemUsageLineResponse(
                    item_id=str(line.item_id),
                    item_name=line.item_name,
                    item_name_am=line.item_name_am,
                    unit_id=str(line.unit_id),
                    unit_code=line.unit_code,
                    unit_name=line.unit_name,
                    unit_name_am=line.unit_name_am,
                    total_quantity=line.total_quantity.format(),
                    total_quantity_milli=line.total_quantity.milli,
                    total_amount=MoneyView.of(line.total_amount),
                    entry_count=line.entry_count,
                )
                for line in report.lines
            ],
        )
