"""Clock adapters."""

from __future__ import annotations

from datetime import UTC, date, datetime

from kise.shared_kernel.application.ports import Clock


class SystemClock(Clock):
    """Reads the real clock. The only place in the codebase allowed to."""

    def now(self) -> datetime:
        return datetime.now(UTC)

    def today(self) -> date:
        return self.now().date()


class FixedClock(Clock):
    """A clock that does not move, for tests and for reproducing a bug on a given day."""

    def __init__(self, moment: datetime) -> None:
        if moment.tzinfo is None:
            raise ValueError("FixedClock needs a timezone-aware datetime")
        self._moment = moment

    def now(self) -> datetime:
        return self._moment

    def today(self) -> date:
        return self._moment.date()

    def advance_to(self, moment: datetime) -> None:
        self._moment = moment
