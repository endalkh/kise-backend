"""The Unit of Measurement application service.

Units are global — one shared table for the whole install — so this service is not owner-scoped the
way categories are. Its two jobs are listing the units a picker shows and letting an admin add a new
one, with the code kept unique so an expense can always resolve the unit it was recorded against.

Deletion is deliberately absent for now: a unit referenced by even one expense must not vanish, and
the seeded system units are permanent. If custom-unit deletion is wanted later, it belongs here,
guarded by ``expenses.count_for_unit`` and ``SystemUnitProtected``.
"""

from __future__ import annotations

from kise.expense_tracking.application.commands import CreateUnitCommand
from kise.expense_tracking.application.views import UnitView
from kise.expense_tracking.domain.errors import UnitCodeTaken
from kise.expense_tracking.domain.models import UnitOfMeasurement
from kise.expense_tracking.infrastructure.persistence.repositories import (
    SqlAlchemyUnitOfMeasurementRepository,
)
from kise.shared_kernel.application.ports import UnitOfWork


class UnitService:
    def __init__(
        self,
        units: SqlAlchemyUnitOfMeasurementRepository,
        uow: UnitOfWork,
    ) -> None:
        self._units = units
        self._uow = uow

    def list(self) -> list[UnitView]:
        return [UnitView.of(unit) for unit in self._units.list_all()]

    def create(self, command: CreateUnitCommand) -> UnitView:
        # The code is the stable identity; the domain normalises it, so check the normalised form.
        normalised = command.code.strip().lower().replace(" ", "")
        if self._units.find_by_code(normalised) is not None:
            raise UnitCodeTaken(normalised)
        unit = UnitOfMeasurement.create(
            code=command.code, name=command.name, name_am=command.name_am, is_system=False
        )
        self._units.add(unit)
        self._uow.commit()
        return UnitView.of(unit)

    def seed_defaults(self, units: list[UnitOfMeasurement]) -> int:
        """Insert the default units if the table is empty. Idempotent — returns how many it added.

        Called once at startup by the composition root. Because units are global, this is not tied
        to any owner or event; it just ensures the picker has something in it on a fresh database.
        """
        if self._units.count() > 0:
            return 0
        self._units.add_all(units)
        self._uow.commit()
        return len(units)
