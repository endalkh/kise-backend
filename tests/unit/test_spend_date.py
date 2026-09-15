from datetime import date

import pytest

from kise.shared_kernel.domain.calendar import CalendarKind, Period, SpendDate
from kise.shared_kernel.domain.errors import ValidationError


def test_entered_in_ethiopian_keeps_the_gregorian_value_canonical():
    spend = SpendDate.from_ethiopian(2018, 11, 15)
    assert spend.gregorian == date(2026, 7, 22)
    assert spend.entered_in is CalendarKind.ETHIOPIAN
    assert spend.ethiopian.iso == "2018-11-15"


def test_same_day_entered_either_way_is_the_same_gregorian_day():
    """FR-2.3: the calendar of entry must not change what gets stored."""
    from_et = SpendDate.from_ethiopian(2018, 11, 15)
    from_greg = SpendDate.from_gregorian(date(2026, 7, 22))
    assert from_et.gregorian == from_greg.gregorian
    assert from_et != from_greg  # they differ only in how they were entered


def test_parse_in_both_calendars():
    assert SpendDate.parse("2018-11-15", "ethiopian").gregorian == date(2026, 7, 22)
    assert SpendDate.parse("2026-07-22", "gregorian").gregorian == date(2026, 7, 22)
    with pytest.raises(ValidationError):
        SpendDate.parse("22/07/2026", "gregorian")


def test_period_views():
    spend = SpendDate.from_ethiopian(2018, 11, 15)
    assert spend.period(CalendarKind.ETHIOPIAN) == Period(CalendarKind.ETHIOPIAN, 2018, 11)
    assert spend.period(CalendarKind.GREGORIAN) == Period(CalendarKind.GREGORIAN, 2026, 7)
    assert spend.own_period == Period(CalendarKind.ETHIOPIAN, 2018, 11)


def test_labels():
    spend = SpendDate.from_ethiopian(2018, 11, 15)
    assert spend.label(CalendarKind.ETHIOPIAN, "am") == "ሐምሌ 15, 2018"
    assert spend.label(CalendarKind.ETHIOPIAN, "en") == "Hamle 15, 2018"
    assert spend.label(CalendarKind.GREGORIAN) == "July 22, 2026"


def test_describe_carries_both_calendars():
    payload = SpendDate.from_gregorian(date(2026, 9, 4)).describe()
    assert payload["gregorian"] == "2026-09-04"
    assert payload["ethiopian"] == "2018-12-29"
    assert payload["ethiopian_month_name_am"] == "ነሐሴ"
    assert payload["weekday_am"] == "ዓርብ"  # 2026-09-04 is a Friday
    assert payload["entered_in"] == "gregorian"


def test_ordering():
    assert SpendDate.from_gregorian(date(2026, 1, 1)) < SpendDate.from_gregorian(date(2026, 1, 2))
    assert SpendDate.from_ethiopian(2018, 1, 1) <= SpendDate.from_ethiopian(2018, 1, 1)


def test_rejects_non_dates():
    with pytest.raises(ValidationError):
        SpendDate("2026-09-04")  # type: ignore[arg-type]
