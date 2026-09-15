"""The month-end item-usage report.

The feature the whole item line exists to serve: at the end of a month, show how much of each item
was bought, in its unit — "Sugar: 12 kg", "Cooking oil: 8 l" — with the money spent alongside, and a
shape the app can turn into a chart.

It is a **read model**. The aggregation happens in SQL (``expenses.item_usage``), grouped by item
and unit, because a unit is what makes a total meaningful: you cannot add 3 kg to 2 pieces. The
service
then decorates the raw sums with item and unit names, and returns lines sorted by spend so the chart
leads with what mattered most.
"""

from __future__ import annotations

from kise.expense_tracking.application.commands import ItemUsageQuery
from kise.expense_tracking.application.views import ItemUsageLine, ItemUsageReport
from kise.expense_tracking.domain.models import Quantity
from kise.expense_tracking.infrastructure.persistence.repositories import (
    SqlAlchemyExpenseRepository,
    SqlAlchemyItemRepository,
    SqlAlchemyUnitOfMeasurementRepository,
)
from kise.shared_kernel.domain.identifiers import ItemId, UnitId
from kise.shared_kernel.domain.money import Money


class ItemUsageService:
    def __init__(
        self,
        expenses: SqlAlchemyExpenseRepository,
        items: SqlAlchemyItemRepository,
        units: SqlAlchemyUnitOfMeasurementRepository,
        *,
        currency: str = "ETB",
    ) -> None:
        self._expenses = expenses
        self._items = items
        self._units = units
        self._currency = currency

    def for_period(self, query: ItemUsageQuery) -> ItemUsageReport:
        period = query.period.resolve()
        since, until = period.gregorian_span
        rows = self._expenses.item_usage(query.owner_id, since, until)

        items = {
            item.id: item
            for item in self._items.list_for_owner(query.owner_id, include_archived=True)
        }
        units = {unit.id: unit for unit in self._units.list_all()}

        lines: list[ItemUsageLine] = []
        for item_uuid, unit_uuid, qty_milli, amount_minor, count in rows:
            item = items.get(ItemId(item_uuid))
            unit = units.get(UnitId(unit_uuid))
            if item is None or unit is None:  # pragma: no cover - referential integrity holds
                continue
            lines.append(
                ItemUsageLine(
                    item_id=item.id,
                    item_name=item.name,
                    item_name_am=item.name_am,
                    unit_id=unit.id,
                    unit_code=unit.code,
                    unit_name=unit.name,
                    unit_name_am=unit.name_am,
                    total_quantity=Quantity(qty_milli),
                    total_amount=Money(amount_minor, self._currency),
                    entry_count=count,
                )
            )

        # Lead with the biggest spend, so the chart's first bar is the one that matters.
        lines.sort(key=lambda line: line.total_amount.minor_units, reverse=True)
        return ItemUsageReport(period=period, lines=tuple(lines), currency=self._currency)
