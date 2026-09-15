"""The FixedExpense aggregate — a monthly commitment, and the months it has been settled in.

This is the richest aggregate in Kise and the reason the model is shaped this way.

*Anchor Calendar.* A commitment recurs in the calendar it was created in. "Rent from ሐምሌ 2018"
produces one Occurrence per **Ethiopian** month forever, so it can never drift against Gregorian
month boundaries. Asking for a Gregorian month still works: the Period is mapped to the anchor
Period it shares the most days with.

*Settlements live inside this aggregate.* "At most one Settlement per Period" is a true invariant,
and an invariant has to be enforceable inside a single aggregate within a single transaction. Filing
Settlements as their own aggregate would demote that rule to a database unique index — enforced by
the storage engine instead of the model. The aggregate stays small: a few dozen Settlements over the
life of a commitment.
"""

from __future__ import annotations

from datetime import date

from kise.expense_tracking.domain.errors import (
    AlreadySettled,
    NotSettled,
    PeriodNotActive,
)
from kise.expense_tracking.domain.events import FixedExpenseScheduled, OccurrenceSettled
from kise.expense_tracking.domain.value_objects.due_day import DueDay
from kise.expense_tracking.domain.value_objects.occurrence import Occurrence
from kise.expense_tracking.domain.value_objects.values import (
    MAX_TITLE_LENGTH,
    clean_note,
    clean_required_text,
)
from kise.shared_kernel.domain.calendar.calendar_kind import CalendarKind
from kise.shared_kernel.domain.calendar.period import Period
from kise.shared_kernel.domain.calendar.period_range import PeriodRange
from kise.shared_kernel.domain.entity import AggregateRoot, Entity
from kise.shared_kernel.domain.errors import InvariantViolation, ValidationError
from kise.shared_kernel.domain.identifiers import (
    CategoryId,
    FixedExpenseId,
    OwnerId,
    SettlementId,
)
from kise.shared_kernel.domain.money import Money


class Settlement(Entity):
    """The record that one Period of a commitment was actually paid.

    Child entity: it has identity and a lifecycle, but it is only ever reached through its
    FixedExpense root.
    """

    def __init__(
        self,
        settlement_id: SettlementId,
        *,
        period: Period,
        amount: Money,
        settled_on: date,
    ) -> None:
        super().__init__(settlement_id)
        if not isinstance(period, Period):
            raise ValidationError("period must be a Period", field="period")
        if not isinstance(amount, Money) or not amount.is_positive:
            raise InvariantViolation("A settled amount must be greater than zero")
        if not isinstance(settled_on, date):
            raise ValidationError("settled_on must be a date", field="settled_on")
        self._period = period
        self._amount = amount
        self._settled_on = settled_on

    @property
    def id(self) -> SettlementId:
        return self._id  # type: ignore[return-value]

    @property
    def period(self) -> Period:
        return self._period

    @property
    def amount(self) -> Money:
        return self._amount

    @property
    def settled_on(self) -> date:
        return self._settled_on

    def correct(self, *, amount: Money | None = None, settled_on: date | None = None) -> None:
        """Fix a mistake in a recorded payment without unsettling the Period."""
        if amount is not None:
            if not amount.is_positive:
                raise InvariantViolation("A settled amount must be greater than zero")
            if amount.currency != self._amount.currency:
                raise InvariantViolation("A settlement cannot change currency")
            self._amount = amount
        if settled_on is not None:
            if not isinstance(settled_on, date):
                raise ValidationError("settled_on must be a date", field="settled_on")
            self._settled_on = settled_on


class FixedExpense(AggregateRoot):
    """A commitment that repeats every month in its Anchor Calendar."""

    def __init__(
        self,
        fixed_expense_id: FixedExpenseId,
        *,
        owner_id: OwnerId,
        category_id: CategoryId,
        title: str,
        amount: Money,
        start_period: Period,
        end_period: Period | None = None,
        due_day: int = 1,
        note: str | None = None,
        is_paused: bool = False,
        settlements: list[Settlement] | None = None,
    ) -> None:
        super().__init__(fixed_expense_id)
        # PeriodRange owns the "same Anchor Calendar" and "end not before start" rules; DueDay owns
        # the 1..30 rule. This aggregate no longer restates either.
        span = PeriodRange(start_period, end_period)
        if not isinstance(amount, Money) or not amount.is_positive:
            raise InvariantViolation("A fixed monthly expense must be greater than zero")

        self._owner_id = owner_id
        self._category_id = category_id
        self._title = clean_required_text(title, field="title", max_length=MAX_TITLE_LENGTH)
        self._amount = amount
        self._span = span
        self._due_day = DueDay.of(due_day)
        self._note = clean_note(note)
        self._is_paused = is_paused
        self._settlements: list[Settlement] = list(settlements or [])

    @classmethod
    def schedule(
        cls,
        *,
        owner_id: OwnerId,
        category_id: CategoryId,
        title: str,
        amount: Money,
        start_period: Period,
        end_period: Period | None = None,
        due_day: int = 1,
        note: str | None = None,
        fixed_expense_id: FixedExpenseId | None = None,
    ) -> FixedExpense:
        commitment = cls(
            fixed_expense_id or FixedExpenseId.new(),
            owner_id=owner_id,
            category_id=category_id,
            title=title,
            amount=amount,
            start_period=start_period,
            end_period=end_period,
            due_day=due_day,
            note=note,
        )
        commitment.record_event(
            FixedExpenseScheduled(
                fixed_expense_id=commitment.id,
                owner_id=owner_id,
                title=commitment.title,
                amount=amount,
                anchor_calendar=start_period.calendar.value,
                start_period=str(start_period),
            )
        )
        return commitment

    # -- state ----------------------------------------------------------
    @property
    def id(self) -> FixedExpenseId:
        return self._id  # type: ignore[return-value]

    @property
    def owner_id(self) -> OwnerId:
        return self._owner_id

    @property
    def category_id(self) -> CategoryId:
        return self._category_id

    @property
    def title(self) -> str:
        return self._title

    @property
    def amount(self) -> Money:
        return self._amount

    @property
    def anchor_calendar(self) -> CalendarKind:
        """The calendar this commitment recurs in. Taken from its active span."""
        return self._span.calendar

    @property
    def active_span(self) -> PeriodRange:
        """The run of Periods this commitment covers."""
        return self._span

    @property
    def start_period(self) -> Period:
        return self._span.start

    @property
    def end_period(self) -> Period | None:
        return self._span.end

    @property
    def is_open_ended(self) -> bool:
        return self._span.is_open_ended

    @property
    def due_day(self) -> DueDay:
        return self._due_day

    @property
    def note(self) -> str | None:
        return self._note

    @property
    def is_paused(self) -> bool:
        return self._is_paused

    @property
    def settlements(self) -> tuple[Settlement, ...]:
        return tuple(self._settlements)

    # -- Period mapping -------------------------------------------------
    def anchor_period_for(self, period: Period) -> Period:
        """The Period in this commitment's Anchor Calendar that ``period`` refers to."""
        return period.as_calendar(self.anchor_calendar)

    def is_active_in(self, period: Period) -> bool:
        """Is this commitment owed in the given Period? Paused commitments are never owed."""
        if self._is_paused:
            return False
        return self._span.contains(period)

    # -- Occurrences ----------------------------------------------------
    def settlement_for(self, period: Period) -> Settlement | None:
        anchor = self.anchor_period_for(period)
        for settlement in self._settlements:
            if settlement.period == anchor:
                return settlement
        return None

    def is_settled_in(self, period: Period) -> bool:
        return self.settlement_for(period) is not None

    def occurrence_for(self, period: Period) -> Occurrence | None:
        """The Occurrence owed in ``period``, or ``None`` when nothing is owed."""
        if not self.is_active_in(period):
            return None
        anchor = self.anchor_period_for(period)
        settlement = self.settlement_for(anchor)
        return Occurrence(
            fixed_expense_id=self.id,
            category_id=self._category_id,
            title=self._title,
            period=anchor,
            due_date=self._due_day.on(anchor),
            # A settled Period keeps what was actually paid, so later edits cannot rewrite
            # history (FR-5.7).
            amount=settlement.amount if settlement else self._amount,
            is_settled=settlement is not None,
            settled_on=settlement.settled_on if settlement else None,
        )

    def occurrences_between(self, first: Period, last: Period) -> list[Occurrence]:
        """Every Occurrence from ``first`` to ``last`` inclusive, in the caller's calendar."""
        found = [self.occurrence_for(period) for period in first.iterate_to(last)]
        return [occurrence for occurrence in found if occurrence is not None]

    # -- settling -------------------------------------------------------
    def settle(
        self,
        period: Period,
        *,
        settled_on: date,
        amount: Money | None = None,
        settlement_id: SettlementId | None = None,
    ) -> Settlement:
        """Record that a Period was paid.

        ``amount`` may differ from the commitment's amount — the electricity bill is rarely the
        number you budgeted. Omit it to settle for the committed amount.
        """
        anchor = self.anchor_period_for(period)
        if self._is_paused:
            raise PeriodNotActive(anchor)
        if not self.is_active_in(anchor):
            raise PeriodNotActive(anchor)
        if self.settlement_for(anchor) is not None:
            raise AlreadySettled(anchor)

        settled_amount = amount if amount is not None else self._amount
        if settled_amount.currency != self._amount.currency:
            raise InvariantViolation(
                "A settlement must use the same currency as the commitment",
                expected=self._amount.currency,
                given=settled_amount.currency,
            )
        settlement = Settlement(
            settlement_id or SettlementId.new(),
            period=anchor,
            amount=settled_amount,
            settled_on=settled_on,
        )
        self._settlements.append(settlement)
        self.record_event(
            OccurrenceSettled(
                fixed_expense_id=self.id,
                owner_id=self._owner_id,
                period=str(anchor),
                amount=settled_amount,
                settled_on=settled_on,
            )
        )
        return settlement

    def unsettle(self, period: Period) -> None:
        """Undo a recorded payment."""
        anchor = self.anchor_period_for(period)
        settlement = self.settlement_for(anchor)
        if settlement is None:
            raise NotSettled(anchor)
        self._settlements.remove(settlement)

    def correct_settlement(
        self, period: Period, *, amount: Money | None = None, settled_on: date | None = None
    ) -> Settlement:
        anchor = self.anchor_period_for(period)
        settlement = self.settlement_for(anchor)
        if settlement is None:
            raise NotSettled(anchor)
        settlement.correct(amount=amount, settled_on=settled_on)
        return settlement

    # -- editing --------------------------------------------------------
    def retitle(self, title: str) -> None:
        self._title = clean_required_text(title, field="title", max_length=MAX_TITLE_LENGTH)

    def change_amount(self, amount: Money) -> None:
        """Change the committed amount.

        Only unsettled Periods are affected: settled ones read their amount from the Settlement,
        so history is left alone (FR-5.7).
        """
        if not isinstance(amount, Money) or not amount.is_positive:
            raise InvariantViolation("A fixed monthly expense must be greater than zero")
        if amount.currency != self._amount.currency:
            raise InvariantViolation(
                "A commitment cannot change currency",
                was=self._amount.currency,
                given=amount.currency,
            )
        self._amount = amount

    def recategorise(self, category_id: CategoryId) -> None:
        self._category_id = category_id

    def change_due_day(self, due_day: int | DueDay) -> None:
        self._due_day = DueDay.of(due_day)

    def amend_note(self, note: str | None) -> None:
        self._note = clean_note(note)

    def end_after(self, end_period: Period | None) -> None:
        """Close the commitment at ``end_period``, or reopen it with ``None``.

        Closing before a Period that has already been settled is refused: that settlement would
        become unreachable and the money would vanish from reports.
        """
        if end_period is None:
            self._span = self._span.with_end(None)
            return
        candidate = self._span.with_end(end_period)
        latest_settled = max(
            (settlement.period for settlement in self._settlements),
            key=lambda period: period.index,
            default=None,
        )
        if latest_settled is not None and end_period < latest_settled:
            raise InvariantViolation(
                "Cannot end before a Period that has already been settled",
                settled=str(latest_settled),
                given=str(end_period),
            )
        self._span = candidate

    def start_from(self, start_period: Period) -> None:
        """Move the first Period, keeping the Anchor Calendar and all settlements reachable."""
        candidate = self._span.with_start(start_period)
        earliest_settled = min(
            (settlement.period for settlement in self._settlements),
            key=lambda period: period.index,
            default=None,
        )
        if earliest_settled is not None and start_period > earliest_settled:
            raise InvariantViolation(
                "Cannot start after a Period that has already been settled",
                settled=str(earliest_settled),
                given=str(start_period),
            )
        self._span = candidate

    def pause(self) -> None:
        if self._is_paused:
            raise InvariantViolation(f"{self._title!r} is already paused")
        self._is_paused = True

    def resume(self) -> None:
        if not self._is_paused:
            raise InvariantViolation(f"{self._title!r} is not paused")
        self._is_paused = False
