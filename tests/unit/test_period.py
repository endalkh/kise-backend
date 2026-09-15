from datetime import date

import pytest

from kise.shared_kernel.domain.calendar import CalendarKind, CalendarMismatch, Period
from kise.shared_kernel.domain.errors import ValidationError

HAMLE_2018 = Period(CalendarKind.ETHIOPIAN, 2018, 11)
JULY_2026 = Period(CalendarKind.GREGORIAN, 2026, 7)


def test_ethiopian_period_accepts_thirteen_months():
    assert Period(CalendarKind.ETHIOPIAN, 2018, 13).month == 13
    with pytest.raises(ValidationError):
        Period(CalendarKind.ETHIOPIAN, 2018, 14)


def test_gregorian_period_stops_at_twelve():
    with pytest.raises(ValidationError):
        Period(CalendarKind.GREGORIAN, 2026, 13)


def test_index_orders_months_inside_one_calendar():
    assert HAMLE_2018.index == 2018 * 13 + 10
    assert HAMLE_2018 < HAMLE_2018.next
    assert HAMLE_2018.previous < HAMLE_2018
    assert HAMLE_2018.months_until(Period(CalendarKind.ETHIOPIAN, 2019, 1)) == 3


def test_next_rolls_pagumen_into_meskerem():
    pagumen = Period(CalendarKind.ETHIOPIAN, 2018, 13)
    assert pagumen.next == Period(CalendarKind.ETHIOPIAN, 2019, 1)
    assert Period(CalendarKind.ETHIOPIAN, 2019, 1).previous == pagumen


def test_next_rolls_december_into_january():
    december = Period(CalendarKind.GREGORIAN, 2026, 12)
    assert december.next == Period(CalendarKind.GREGORIAN, 2027, 1)
    assert Period(CalendarKind.GREGORIAN, 2027, 1).previous == december


def test_cross_calendar_ordering_is_refused():
    with pytest.raises(CalendarMismatch):
        _ = HAMLE_2018 < JULY_2026
    with pytest.raises(CalendarMismatch):
        HAMLE_2018.months_until(JULY_2026)


def test_length_in_days():
    assert HAMLE_2018.length_in_days == 30
    assert Period(CalendarKind.ETHIOPIAN, 2018, 13).length_in_days == 5
    assert Period(CalendarKind.ETHIOPIAN, 2019, 13).length_in_days == 6  # leap
    assert Period(CalendarKind.GREGORIAN, 2024, 2).length_in_days == 29
    assert Period(CalendarKind.GREGORIAN, 2025, 2).length_in_days == 28


def test_day_clamps_to_the_period_length():
    # A commitment due on the 30th, seen in ጳጉሜን (5 days) -> last day of ጳጉሜን.
    assert Period(CalendarKind.ETHIOPIAN, 2018, 13).day(30) == date(2026, 9, 10)
    # Same idea in February.
    assert Period(CalendarKind.GREGORIAN, 2025, 2).day(30) == date(2025, 2, 28)
    assert Period(CalendarKind.GREGORIAN, 2024, 2).day(30) == date(2024, 2, 29)
    # Normal case is untouched.
    assert HAMLE_2018.day(15) == date(2026, 7, 22)
    with pytest.raises(ValidationError):
        HAMLE_2018.day(0)


def test_gregorian_span_of_an_ethiopian_period():
    assert HAMLE_2018.gregorian_span == (date(2026, 7, 8), date(2026, 8, 6))


def test_gregorian_span_of_a_gregorian_period():
    assert JULY_2026.gregorian_span == (date(2026, 7, 1), date(2026, 7, 31))


def test_from_date_picks_the_containing_period():
    assert Period.from_date(date(2026, 7, 22), CalendarKind.ETHIOPIAN) == HAMLE_2018
    assert Period.from_date(date(2026, 7, 22), CalendarKind.GREGORIAN) == JULY_2026


def test_contains():
    assert HAMLE_2018.contains(date(2026, 7, 8))
    assert HAMLE_2018.contains(date(2026, 8, 6))
    assert not HAMLE_2018.contains(date(2026, 8, 7))


def test_overlaps_is_symmetric_across_calendars():
    assert HAMLE_2018.overlaps(JULY_2026)
    assert JULY_2026.overlaps(HAMLE_2018)
    # ሐምሌ 2018 runs 8 Jul - 6 Aug 2026, so it does not reach September.
    september = Period(CalendarKind.GREGORIAN, 2026, 9)
    assert not HAMLE_2018.overlaps(september)
    assert not september.overlaps(HAMLE_2018)


def test_every_ethiopian_period_overlaps_exactly_two_gregorian_periods():
    """This is what guarantees one Occurrence per month when calendars are mixed."""
    for month in range(1, 13):
        period = Period(CalendarKind.ETHIOPIAN, 2018, month)
        overlapping = [
            g
            for g in (
                Period(CalendarKind.GREGORIAN, y, m)
                for y in (2025, 2026, 2027)
                for m in range(1, 13)
            )
            if period.overlaps(g)
        ]
        assert len(overlapping) == 2, (period, overlapping)


def test_as_calendar_converts_by_first_day():
    assert HAMLE_2018.as_calendar(CalendarKind.GREGORIAN) == JULY_2026
    assert HAMLE_2018.as_calendar(CalendarKind.ETHIOPIAN) is HAMLE_2018


def test_overlap_days():
    # ሐምሌ 2018 runs 8 Jul - 6 Aug 2026: 24 days in July, 6 in August.
    assert HAMLE_2018.overlap_days(JULY_2026) == 24
    assert HAMLE_2018.overlap_days(Period(CalendarKind.GREGORIAN, 2026, 8)) == 6
    assert HAMLE_2018.overlap_days(Period(CalendarKind.GREGORIAN, 2026, 9)) == 0
    assert HAMLE_2018.overlap_days(HAMLE_2018) == 30


def test_as_calendar_picks_the_period_sharing_the_most_days():
    assert HAMLE_2018.as_calendar(CalendarKind.GREGORIAN) == JULY_2026
    assert HAMLE_2018.as_calendar(CalendarKind.ETHIOPIAN) is HAMLE_2018
    # And back again, so the mapping is stable in both directions for this pair.
    assert JULY_2026.as_calendar(CalendarKind.ETHIOPIAN) == HAMLE_2018


def test_as_calendar_is_injective_across_a_year():
    """Distinct Gregorian months must map to distinct Ethiopian anchors, or a commitment would
    be billed twice in one month and skipped in another."""
    months = [Period(CalendarKind.GREGORIAN, 2026, m) for m in range(1, 13)]
    anchors = [m.as_calendar(CalendarKind.ETHIOPIAN) for m in months]
    assert len(set(anchors)) == 12

    et_months = Period(CalendarKind.ETHIOPIAN, 2018, 1).iterate_to(
        Period(CalendarKind.ETHIOPIAN, 2018, 13)
    )
    assert len({p.as_calendar(CalendarKind.GREGORIAN) for p in et_months}) == 13


def test_iterate_to():
    periods = HAMLE_2018.iterate_to(Period(CalendarKind.ETHIOPIAN, 2019, 1))
    assert [p.month for p in periods] == [11, 12, 13, 1]
    assert [p.year for p in periods] == [2018, 2018, 2018, 2019]


def test_labels_are_bilingual_and_dual_calendar():
    assert HAMLE_2018.label("am") == "ሐምሌ 2018"
    assert HAMLE_2018.label("en") == "Hamle 2018"
    assert HAMLE_2018.counterpart_label("en") == "July - August 2026"
    assert JULY_2026.label("en") == "July 2026"
    assert JULY_2026.counterpart_label("am") == "ሰኔ - ሐምሌ 2018"

    payload = HAMLE_2018.labels()
    assert payload["calendar"] == "ethiopian"
    assert payload["first_day"] == "2026-07-08"
    assert payload["last_day"] == "2026-08-06"


def test_counterpart_label_across_a_year_boundary():
    tahsas = Period(CalendarKind.ETHIOPIAN, 2018, 4)  # ~10 Dec 2025 - 8 Jan 2026
    assert tahsas.counterpart_label("en") == "December 2025 - January 2026"


def test_period_is_a_value_object():
    assert Period(CalendarKind.ETHIOPIAN, 2018, 11) == HAMLE_2018
    assert len({HAMLE_2018, Period(CalendarKind.ETHIOPIAN, 2018, 11), JULY_2026}) == 2
    assert Period.of("ethiopian", 2018, 11) == HAMLE_2018
