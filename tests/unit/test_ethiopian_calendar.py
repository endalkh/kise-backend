from datetime import date, timedelta

import pytest

from kise.shared_kernel.domain.calendar import ethiopian as ec

# Known-good anchors, independently verifiable.
# (ethiopian_year, ethiopian_month, ethiopian_day, gregorian_date)
ANCHORS = [
    # Before 1900 the mapping sits one day earlier: Gregorian skipped the 1900 leap day
    # but the Ethiopian calendar has no century exception.
    (1855, 1, 1, date(1862, 9, 10)),
    (1992, 4, 22, date(2000, 1, 1)),  # Gregorian millennium
    (2000, 1, 1, date(2007, 9, 12)),  # Ethiopian millennium (Enkutatash 2000)
    (2007, 5, 8, date(2015, 1, 16)),
    (2012, 7, 22, date(2020, 3, 31)),
    (2016, 4, 22, date(2024, 1, 1)),
    (2016, 6, 21, date(2024, 2, 29)),  # Gregorian leap day
    (2017, 13, 5, date(2025, 9, 10)),  # last day of a non-leap Ethiopian year
    (2018, 12, 29, date(2026, 9, 4)),
    (2019, 13, 6, date(2027, 9, 11)),  # Pagumen 6 in an Ethiopian leap year
]


@pytest.mark.parametrize(("year", "month", "day", "gregorian"), ANCHORS)
def test_ethiopian_to_gregorian(year, month, day, gregorian):
    assert ec.ethiopian_to_gregorian(year, month, day) == gregorian


@pytest.mark.parametrize(("year", "month", "day", "gregorian"), ANCHORS)
def test_gregorian_to_ethiopian(year, month, day, gregorian):
    assert ec.gregorian_to_ethiopian(gregorian) == (year, month, day)


def test_round_trip_over_40_years():
    """Every single day for 40 years must survive a round trip."""
    current = date(1990, 1, 1)
    end = date(2030, 1, 1)
    while current <= end:
        et = ec.EthiopianDate.from_gregorian(current)
        assert et.to_gregorian() == current, et
        current += timedelta(days=1)


def test_century_shift_is_intentional():
    """The Ethiopian calendar has no century exception, so the offset changes at 1900.

    Meskerem 1 is 29 or 30 August in the Julian calendar, always. Gregorian 1900 was not a
    leap year while the Julian/Ethiopian cycle carried on, so the Gregorian equivalent of the
    Ethiopian new year sits on 10/11 September in the 19th century and on 11/12 September
    afterwards. Both branches are correct; only the Gregorian label moves.
    """
    assert ec.ethiopian_to_gregorian(1889, 1, 1) == date(1896, 9, 10)
    assert ec.ethiopian_to_gregorian(1891, 1, 1) == date(1898, 9, 10)
    assert ec.ethiopian_to_gregorian(1892, 1, 1) == date(1899, 9, 11)
    assert ec.ethiopian_to_gregorian(1896, 1, 1) == date(1903, 9, 12)
    # Post-1900 the familiar rule holds, which the next test asserts for 1990-2050.
    assert ec.ethiopian_to_gregorian(2018, 1, 1) == date(2025, 9, 11)


def test_new_year_day_matches_september_11_or_12():
    for gregorian_year in range(1990, 2051):
        et_year = gregorian_year - 7
        new_year = ec.ethiopian_to_gregorian(et_year, 1, 1)
        assert new_year.month == 9
        assert new_year.day in (11, 12)
        # September 12 exactly when the *following* Gregorian year is a leap year.
        following_is_leap = (gregorian_year + 1) % 4 == 0 and (
            (gregorian_year + 1) % 100 != 0 or (gregorian_year + 1) % 400 == 0
        )
        assert new_year.day == (12 if following_is_leap else 11), gregorian_year


@pytest.mark.parametrize(
    ("year", "expected"),
    [(2011, True), (2015, True), (2019, True), (2016, False), (2017, False), (2018, False)],
)
def test_leap_years(year, expected):
    assert ec.is_ethiopian_leap_year(year) is expected
    assert ec.ethiopian_month_length(year, 13) == (6 if expected else 5)


def test_regular_months_have_30_days():
    for month in range(1, 13):
        assert ec.ethiopian_month_length(2017, month) == 30


def test_month_names_are_amharic_and_complete():
    assert len(ec.ETHIOPIAN_MONTH_NAMES_AM) == 13
    assert len(ec.ETHIOPIAN_MONTH_NAMES_EN) == 13
    assert ec.ETHIOPIAN_MONTH_NAMES_AM[0] == "መስከረም"
    assert ec.ETHIOPIAN_MONTH_NAMES_AM[10] == "ሐምሌ"  # Hamle
    assert ec.ETHIOPIAN_MONTH_NAMES_AM[11] == "ነሐሴ"  # Nehase
    assert ec.ETHIOPIAN_MONTH_NAMES_EN[10] == "Hamle"
    assert ec.ETHIOPIAN_MONTH_NAMES_EN[11] == "Nehase"


def test_invalid_dates_rejected():
    with pytest.raises(ec.EthiopianDateError):
        ec.EthiopianDate(2017, 13, 6)  # 2017 is not a leap year -> Pagumen has 5 days
    with pytest.raises(ec.EthiopianDateError):
        ec.EthiopianDate(2017, 14, 1)
    with pytest.raises(ec.EthiopianDateError):
        ec.EthiopianDate(2017, 1, 31)
    with pytest.raises(ec.EthiopianDateError):
        ec.EthiopianDate(2017, 1, 0)


def test_ethiopian_month_bounds():
    first, last = ec.ethiopian_month_bounds(2018, 11)  # Hamle 2018
    assert first == date(2026, 7, 8)
    assert last == date(2026, 8, 6)


def test_gregorian_month_bounds():
    assert ec.gregorian_month_bounds(2024, 2) == (date(2024, 2, 1), date(2024, 2, 29))
    assert ec.gregorian_month_bounds(2025, 12) == (date(2025, 12, 1), date(2025, 12, 31))


def test_add_months_clamps_into_pagumen():
    # Nehase 30 + 1 month lands in Pagumen which only has 5 days -> clamp to 5.
    assert ec.EthiopianDate(2017, 12, 30).add_months(1) == ec.EthiopianDate(2017, 13, 5)
    # 13th month rolls into the next year.
    assert ec.EthiopianDate(2017, 13, 5).add_months(1) == ec.EthiopianDate(2018, 1, 5)


def test_add_days_crosses_new_year():
    assert ec.EthiopianDate(2017, 13, 5).add_days(1) == ec.EthiopianDate(2018, 1, 1)


def test_parse_and_format():
    et = ec.EthiopianDate.parse("2018-11-15")
    assert (et.year, et.month, et.day) == (2018, 11, 15)
    assert et.iso == "2018-11-15"
    assert et.format("am") == "ሐምሌ 15, 2018"
    assert et.format("en") == "Hamle 15, 2018"
    with pytest.raises(ec.EthiopianDateError):
        ec.EthiopianDate.parse("2018/11/15")


def test_describe_contains_both_calendars():
    payload = ec.describe(date(2026, 9, 4))
    assert payload["gregorian"] == "2026-09-04"
    assert payload["ethiopian"] == "2018-12-29"
    assert payload["ethiopian_month_name_am"] == "ነሐሴ"
    assert payload["gregorian_month_name"] == "September"
