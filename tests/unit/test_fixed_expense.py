from datetime import date

import pytest

from kise.expense_tracking.domain.errors import (
    AlreadySettled,
    NotSettled,
    PeriodNotActive,
)
from kise.expense_tracking.domain.models import FixedExpense
from kise.shared_kernel.domain.calendar import CalendarKind, Period
from kise.shared_kernel.domain.errors import InvariantViolation, ValidationError
from kise.shared_kernel.domain.identifiers import CategoryId, OwnerId
from kise.shared_kernel.domain.money import Money

OWNER = OwnerId.new()
CATEGORY = CategoryId.new()

HAMLE_2018 = Period(CalendarKind.ETHIOPIAN, 2018, 11)
NEHASE_2018 = Period(CalendarKind.ETHIOPIAN, 2018, 12)
PAGUMEN_2018 = Period(CalendarKind.ETHIOPIAN, 2018, 13)
MESKEREM_2019 = Period(CalendarKind.ETHIOPIAN, 2019, 1)
JULY_2026 = Period(CalendarKind.GREGORIAN, 2026, 7)

RENT = Money.from_major("8000")


def rent(**overrides) -> FixedExpense:
    """A rent commitment anchored in the Ethiopian calendar from ሐምሌ 2018."""
    kwargs = {
        "owner_id": OWNER,
        "category_id": CATEGORY,
        "title": "House rent",
        "amount": RENT,
        "start_period": HAMLE_2018,
        "due_day": 5,
    }
    kwargs.update(overrides)
    return FixedExpense.schedule(**kwargs)


# -- scheduling ---------------------------------------------------------


def test_scheduling_announces_itself_and_takes_its_anchor_from_the_start_period():
    commitment = rent()
    assert commitment.anchor_calendar is CalendarKind.ETHIOPIAN
    assert commitment.is_open_ended
    events = commitment.pull_events()
    assert [e.name for e in events] == ["FixedExpenseScheduled"]
    assert events[0].anchor_calendar == "ethiopian"
    assert events[0].start_period == "ethiopian 2018-11"


def test_amount_must_be_positive():
    with pytest.raises(InvariantViolation):
        rent(amount=Money.zero())
    with pytest.raises(InvariantViolation):
        rent(amount=Money(-100))


def test_title_is_required():
    with pytest.raises(ValidationError):
        rent(title="   ")


def test_due_day_is_bounded_to_thirty():
    with pytest.raises(ValidationError):
        rent(due_day=0)
    with pytest.raises(ValidationError):
        rent(due_day=31)
    with pytest.raises(ValidationError):
        rent(due_day=True)


def test_end_period_must_share_the_anchor_calendar_and_follow_the_start():
    with pytest.raises(InvariantViolation):
        rent(end_period=JULY_2026)
    with pytest.raises(InvariantViolation):
        rent(end_period=Period(CalendarKind.ETHIOPIAN, 2018, 10))
    # Same month is fine: a one-month commitment.
    assert rent(end_period=HAMLE_2018).end_period == HAMLE_2018


# -- recurrence in the anchor calendar ---------------------------------


def test_one_occurrence_per_ethiopian_period_for_fourteen_months():
    """FR-5.5: exactly one Occurrence per month, rolling through ጳጉሜን into the new year."""
    commitment = rent()
    periods = HAMLE_2018.iterate_to(Period(CalendarKind.ETHIOPIAN, 2019, 12))
    occurrences = [commitment.occurrence_for(period) for period in periods]
    assert len(occurrences) == 15
    assert all(o is not None for o in occurrences)
    assert [o.period for o in occurrences] == periods
    assert len({o.period for o in occurrences}) == 15


def test_nothing_is_owed_before_the_start_period():
    commitment = rent()
    assert commitment.occurrence_for(Period(CalendarKind.ETHIOPIAN, 2018, 10)) is None
    assert not commitment.is_active_in(Period(CalendarKind.ETHIOPIAN, 2018, 10))


def test_nothing_is_owed_after_the_end_period():
    commitment = rent(end_period=NEHASE_2018)
    assert commitment.occurrence_for(NEHASE_2018) is not None
    assert commitment.occurrence_for(PAGUMEN_2018) is None
    assert commitment.occurrences_between(HAMLE_2018, MESKEREM_2019) == [
        commitment.occurrence_for(HAMLE_2018),
        commitment.occurrence_for(NEHASE_2018),
    ]


def test_paused_commitments_owe_nothing():
    commitment = rent()
    commitment.pause()
    assert commitment.occurrence_for(HAMLE_2018) is None
    assert not commitment.is_active_in(HAMLE_2018)
    commitment.resume()
    assert commitment.occurrence_for(HAMLE_2018) is not None
    with pytest.raises(InvariantViolation):
        commitment.resume()


# -- due dates and clamping -------------------------------------------


def test_due_date_uses_the_anchor_period():
    commitment = rent(due_day=5)
    # ሐምሌ 1, 2018 is 8 July 2026, so ሐምሌ 5 is 12 July 2026.
    assert commitment.occurrence_for(HAMLE_2018).due_date == date(2026, 7, 12)


def test_due_day_thirty_clamps_inside_pagumen():
    """FR-5.3: ጳጉሜን has 5 days, so 'the 30th' becomes its last day."""
    commitment = rent(due_day=30)
    assert commitment.occurrence_for(PAGUMEN_2018).due_date == date(2026, 9, 10)
    assert PAGUMEN_2018.length_in_days == 5


def test_due_day_thirty_clamps_in_february():
    commitment = rent(
        start_period=Period(CalendarKind.GREGORIAN, 2024, 1),
        due_day=30,
    )
    assert commitment.occurrence_for(Period(CalendarKind.GREGORIAN, 2024, 2)).due_date == date(
        2024, 2, 29
    )
    assert commitment.occurrence_for(Period(CalendarKind.GREGORIAN, 2025, 2)).due_date == date(
        2025, 2, 28
    )


# -- cross-calendar viewing -------------------------------------------


def test_an_ethiopian_commitment_seen_in_gregorian_months():
    """FR-5.2: viewing in the other calendar yields one Occurrence per month, no drift."""
    commitment = rent()
    gregorian_months = Period(CalendarKind.GREGORIAN, 2026, 7).iterate_to(
        Period(CalendarKind.GREGORIAN, 2027, 6)
    )
    occurrences = [commitment.occurrence_for(period) for period in gregorian_months]
    assert all(o is not None for o in occurrences)
    assert len(occurrences) == 12
    # Each Gregorian month maps to a distinct Ethiopian anchor Period: no month is billed twice
    # and none is skipped.
    anchors = [o.period for o in occurrences]
    assert len(set(anchors)) == 12
    assert all(a.calendar is CalendarKind.ETHIOPIAN for a in anchors)


def test_the_anchor_period_is_the_one_sharing_the_most_days():
    commitment = rent()
    # ሐምሌ 2018 runs 8 Jul - 6 Aug 2026, so July 2026 (24 shared days) maps to ሐምሌ.
    assert commitment.anchor_period_for(JULY_2026) == HAMLE_2018
    assert commitment.occurrence_for(JULY_2026).period == HAMLE_2018


def test_settling_via_a_gregorian_period_settles_the_anchor_period():
    commitment = rent()
    commitment.settle(JULY_2026, settled_on=date(2026, 7, 12))
    assert commitment.is_settled_in(HAMLE_2018)
    # And the same month cannot then be settled again from either calendar.
    with pytest.raises(AlreadySettled):
        commitment.settle(HAMLE_2018, settled_on=date(2026, 7, 12))


# -- settling ----------------------------------------------------------


def test_settling_defaults_to_the_committed_amount():
    commitment = rent()
    commitment.pull_events()
    settlement = commitment.settle(HAMLE_2018, settled_on=date(2026, 7, 12))
    assert settlement.amount == RENT
    assert settlement.period == HAMLE_2018

    occurrence = commitment.occurrence_for(HAMLE_2018)
    assert occurrence.is_settled
    assert occurrence.settled_on == date(2026, 7, 12)
    assert occurrence.outstanding == Money.zero()
    assert occurrence.settled == RENT

    events = commitment.pull_events()
    assert [e.name for e in events] == ["OccurrenceSettled"]
    assert events[0].period == "ethiopian 2018-11"


def test_settling_can_record_a_different_actual_amount():
    """The electricity bill is rarely the number you budgeted."""
    commitment = rent(title="Electricity", amount=Money.from_major("600"))
    actual = Money.from_major("734.50")
    commitment.settle(HAMLE_2018, settled_on=date(2026, 7, 9), amount=actual)
    assert commitment.occurrence_for(HAMLE_2018).amount == actual


def test_settling_twice_is_refused():
    commitment = rent()
    commitment.settle(HAMLE_2018, settled_on=date(2026, 7, 12))
    with pytest.raises(AlreadySettled):
        commitment.settle(HAMLE_2018, settled_on=date(2026, 7, 13))
    assert len(commitment.settlements) == 1


def test_settling_an_inactive_period_is_refused():
    commitment = rent(end_period=NEHASE_2018)
    with pytest.raises(PeriodNotActive):
        commitment.settle(PAGUMEN_2018, settled_on=date(2026, 9, 1))
    with pytest.raises(PeriodNotActive):
        commitment.settle(Period(CalendarKind.ETHIOPIAN, 2018, 10), settled_on=date(2026, 7, 1))


def test_settling_a_paused_commitment_is_refused():
    commitment = rent()
    commitment.pause()
    with pytest.raises(PeriodNotActive):
        commitment.settle(HAMLE_2018, settled_on=date(2026, 7, 12))


def test_settlement_currency_must_match():
    commitment = rent()
    with pytest.raises(InvariantViolation):
        commitment.settle(
            HAMLE_2018, settled_on=date(2026, 7, 12), amount=Money.from_major("100", "USD")
        )


def test_settled_amount_must_be_positive():
    commitment = rent()
    with pytest.raises(InvariantViolation):
        commitment.settle(HAMLE_2018, settled_on=date(2026, 7, 12), amount=Money.zero())


def test_unsettling_restores_the_committed_amount():
    commitment = rent()
    commitment.settle(HAMLE_2018, settled_on=date(2026, 7, 12), amount=Money.from_major("7500"))
    commitment.unsettle(HAMLE_2018)
    occurrence = commitment.occurrence_for(HAMLE_2018)
    assert occurrence.is_outstanding
    assert occurrence.amount == RENT
    assert commitment.settlements == ()
    with pytest.raises(NotSettled):
        commitment.unsettle(HAMLE_2018)


def test_correcting_a_settlement():
    commitment = rent()
    commitment.settle(HAMLE_2018, settled_on=date(2026, 7, 12))
    commitment.correct_settlement(
        HAMLE_2018, amount=Money.from_major("8100"), settled_on=date(2026, 7, 14)
    )
    occurrence = commitment.occurrence_for(HAMLE_2018)
    assert occurrence.amount == Money.from_major("8100")
    assert occurrence.settled_on == date(2026, 7, 14)
    with pytest.raises(NotSettled):
        commitment.correct_settlement(NEHASE_2018, amount=Money.from_major("1"))


# -- history is immutable ---------------------------------------------


def test_raising_the_amount_leaves_settled_periods_alone():
    """FR-5.7: an edit applies to future months only."""
    commitment = rent()
    commitment.settle(HAMLE_2018, settled_on=date(2026, 7, 12))
    commitment.change_amount(Money.from_major("9000"))

    assert commitment.occurrence_for(HAMLE_2018).amount == RENT  # already paid, untouched
    assert commitment.occurrence_for(NEHASE_2018).amount == Money.from_major("9000")


def test_amount_cannot_change_currency_or_go_to_zero():
    commitment = rent()
    with pytest.raises(InvariantViolation):
        commitment.change_amount(Money.from_major("100", "USD"))
    with pytest.raises(InvariantViolation):
        commitment.change_amount(Money.zero())


def test_cannot_end_before_a_settled_period():
    commitment = rent()
    commitment.settle(NEHASE_2018, settled_on=date(2026, 8, 10))
    with pytest.raises(InvariantViolation):
        commitment.end_after(HAMLE_2018)
    commitment.end_after(NEHASE_2018)
    assert commitment.end_period == NEHASE_2018


def test_cannot_start_after_a_settled_period():
    commitment = rent()
    commitment.settle(HAMLE_2018, settled_on=date(2026, 7, 12))
    with pytest.raises(InvariantViolation):
        commitment.start_from(NEHASE_2018)
    commitment.start_from(Period(CalendarKind.ETHIOPIAN, 2018, 10))
    assert commitment.start_period == Period(CalendarKind.ETHIOPIAN, 2018, 10)


def test_end_and_start_must_stay_in_the_anchor_calendar():
    commitment = rent()
    with pytest.raises(InvariantViolation):
        commitment.end_after(JULY_2026)
    with pytest.raises(InvariantViolation):
        commitment.start_from(JULY_2026)


def test_reopening_an_ended_commitment():
    commitment = rent(end_period=NEHASE_2018)
    commitment.end_after(None)
    assert commitment.is_open_ended
    assert commitment.occurrence_for(MESKEREM_2019) is not None


# -- other edits -------------------------------------------------------


def test_editing_title_note_due_day_and_category():
    commitment = rent()
    commitment.retitle("  Rent   for   the  flat ")
    assert commitment.title == "Rent for the flat"
    commitment.amend_note("   ")
    assert commitment.note is None
    commitment.amend_note("Paid to Ato Bekele")
    assert commitment.note == "Paid to Ato Bekele"
    commitment.change_due_day(28)
    assert commitment.due_day.value == 28
    with pytest.raises(ValidationError):
        commitment.change_due_day(31)
    new_category = CategoryId.new()
    commitment.recategorise(new_category)
    assert commitment.category_id == new_category


def test_pausing_twice_is_refused():
    commitment = rent()
    commitment.pause()
    with pytest.raises(InvariantViolation):
        commitment.pause()
