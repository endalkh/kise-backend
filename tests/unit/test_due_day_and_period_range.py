"""The two value objects extracted from ``FixedExpense``.

Both exist because a rule was being restated: ``due_day`` was validated in the constructor and again
in ``change_due_day``; the start/end rules were checked in the constructor, ``end_after`` and
``start_from``. Now each rule has one home and its own tests.
"""

from datetime import date

import pytest

from kise.expense_tracking.domain.value_objects import MAX_DUE_DAY, DueDay
from kise.shared_kernel.domain.calendar import CalendarKind, Period
from kise.shared_kernel.domain.calendar.period_range import PeriodRange
from kise.shared_kernel.domain.errors import InvariantViolation, ValidationError

HAMLE_2018 = Period(CalendarKind.ETHIOPIAN, 2018, 11)
NEHASE_2018 = Period(CalendarKind.ETHIOPIAN, 2018, 12)
PAGUMEN_2018 = Period(CalendarKind.ETHIOPIAN, 2018, 13)
MESKEREM_2019 = Period(CalendarKind.ETHIOPIAN, 2019, 1)
JULY_2026 = Period(CalendarKind.GREGORIAN, 2026, 7)


# -- DueDay -------------------------------------------------------------


def test_due_day_runs_one_to_thirty():
    assert DueDay(1).value == 1
    assert DueDay(MAX_DUE_DAY).value == 30
    assert MAX_DUE_DAY == 30  # Ethiopian months have 30 days, so 30 means "the last day"


@pytest.mark.parametrize("bad", [0, -1, 31, 32, True, 5.5, "5"])
def test_invalid_due_days_are_refused(bad):
    with pytest.raises(ValidationError):
        DueDay(bad)


def test_of_accepts_either_an_int_or_a_due_day():
    assert DueDay.of(5) == DueDay(5)
    already = DueDay(5)
    assert DueDay.of(already) is already


def test_landing_on_a_period_clamps_to_its_length():
    """The rule that keeps a "due on the 30th" commitment sane in ጳጉሜን and February."""
    assert DueDay(5).on(HAMLE_2018) == date(2026, 7, 12)  # ሐምሌ 1 is 8 July
    assert DueDay(30).on(HAMLE_2018) == date(2026, 8, 6)  # ሐምሌ 30
    assert DueDay(30).on(PAGUMEN_2018) == date(2026, 9, 10)  # ጳጉሜን has 5 days
    assert DueDay(30).on(Period(CalendarKind.GREGORIAN, 2025, 2)) == date(2025, 2, 28)
    assert DueDay(30).on(Period(CalendarKind.GREGORIAN, 2024, 2)) == date(2024, 2, 29)


def test_is_clamped_in_reports_when_the_day_did_not_fit():
    assert DueDay(30).is_clamped_in(PAGUMEN_2018)
    assert not DueDay(5).is_clamped_in(PAGUMEN_2018)
    assert not DueDay(30).is_clamped_in(HAMLE_2018)


def test_due_day_is_a_value_object():
    assert DueDay(5) == DueDay(5)
    assert len({DueDay(5), DueDay(5), DueDay(6)}) == 2
    assert int(DueDay(5)) == 5


# -- PeriodRange --------------------------------------------------------


def test_an_open_ended_range():
    span = PeriodRange(HAMLE_2018)
    assert span.is_open_ended
    assert span.end is None
    assert span.length_in_months is None
    assert span.calendar is CalendarKind.ETHIOPIAN


def test_a_closed_range():
    span = PeriodRange(HAMLE_2018, MESKEREM_2019)
    assert not span.is_open_ended
    assert span.length_in_months == 4  # ሐምሌ, ነሐሴ, ጳጉሜን, መስከረም
    assert [p.month for p in span.periods()] == [11, 12, 13, 1]


def test_the_end_may_equal_the_start():
    span = PeriodRange(HAMLE_2018, HAMLE_2018)
    assert span.length_in_months == 1


def test_end_before_start_is_refused():
    with pytest.raises(InvariantViolation):
        PeriodRange(NEHASE_2018, HAMLE_2018)


def test_both_ends_must_share_the_anchor_calendar():
    with pytest.raises(InvariantViolation):
        PeriodRange(HAMLE_2018, JULY_2026)


def test_a_start_is_required():
    with pytest.raises(ValidationError):
        PeriodRange(None)  # type: ignore[arg-type]
    with pytest.raises(ValidationError):
        PeriodRange(HAMLE_2018, "2019-01")  # type: ignore[arg-type]


def test_contains_within_the_anchor_calendar():
    span = PeriodRange(HAMLE_2018, PAGUMEN_2018)
    assert span.contains(HAMLE_2018)
    assert span.contains(NEHASE_2018)
    assert span.contains(PAGUMEN_2018)
    assert not span.contains(Period(CalendarKind.ETHIOPIAN, 2018, 10))
    assert not span.contains(MESKEREM_2019)


def test_contains_converts_a_foreign_calendar_period():
    """Asking "is this commitment owed in July?" about an Ethiopian-anchored range."""
    span = PeriodRange(HAMLE_2018, PAGUMEN_2018)
    assert span.contains(JULY_2026)  # July 2026 maps to ሐምሌ 2018
    # June 2026 maps to ሰኔ 2018, which is before the start.
    assert not span.contains(Period(CalendarKind.GREGORIAN, 2026, 6))


def test_an_open_ended_range_contains_everything_after_its_start():
    span = PeriodRange(HAMLE_2018)
    assert span.contains(Period(CalendarKind.ETHIOPIAN, 2030, 7))
    assert not span.contains(Period(CalendarKind.ETHIOPIAN, 2018, 10))


def test_listing_the_periods_of_an_open_ended_range_is_refused():
    with pytest.raises(InvariantViolation):
        PeriodRange(HAMLE_2018).periods()


def test_with_end_and_with_start_revalidate():
    span = PeriodRange(HAMLE_2018)
    closed = span.with_end(NEHASE_2018)
    assert closed.end == NEHASE_2018
    assert span.is_open_ended  # the original is untouched: value objects do not mutate

    assert closed.with_end(None).is_open_ended
    assert closed.with_start(Period(CalendarKind.ETHIOPIAN, 2018, 10)).length_in_months == 3

    with pytest.raises(InvariantViolation):
        closed.with_end(JULY_2026)  # wrong calendar
    with pytest.raises(InvariantViolation):
        closed.with_start(JULY_2026)
    with pytest.raises(InvariantViolation):
        closed.with_end(Period(CalendarKind.ETHIOPIAN, 2018, 10))  # before the start


def test_period_range_is_a_value_object():
    assert PeriodRange(HAMLE_2018, NEHASE_2018) == PeriodRange(HAMLE_2018, NEHASE_2018)
    assert PeriodRange(HAMLE_2018) != PeriodRange(HAMLE_2018, NEHASE_2018)
    assert len({PeriodRange(HAMLE_2018), PeriodRange(HAMLE_2018)}) == 1
