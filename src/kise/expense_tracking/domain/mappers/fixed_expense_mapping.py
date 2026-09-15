"""The FixedExpense mapping contract."""

from __future__ import annotations

from typing import Any, Protocol, runtime_checkable

from kise.expense_tracking.domain.models import FixedExpense

__all__ = ["FixedExpenseMapping"]


@runtime_checkable
class FixedExpenseMapping(Protocol):
    """Translates the FixedExpense aggregate — Settlements included — in one go.

    There is no separate Settlement contract. A Settlement is persisted only as part of its
    commitment, so this mapper owns that translation, mirroring the rule that nothing outside the
    aggregate may hold a reference to a Settlement.

    Two things an implementation must get right:

    * a Settlement's Period comes back in the commitment's **Anchor Calendar** — the calendar is
      stored once, on the root, never on the child;
    * ``update_model`` synchronises the whole collection: added Settlements are inserted, removed
      ones deleted, corrected ones updated in place.
    """

    @staticmethod
    def to_model(aggregate: FixedExpense) -> Any: ...

    @staticmethod
    def to_domain(model: Any) -> FixedExpense: ...

    @staticmethod
    def update_model(model: Any, aggregate: FixedExpense) -> None: ...
