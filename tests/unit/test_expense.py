from datetime import date

import pytest

from kise.expense_tracking.domain.models import Expense
from kise.expense_tracking.domain.value_objects import PaymentMethod
from kise.shared_kernel.domain.calendar import CalendarKind, Period, SpendDate
from kise.shared_kernel.domain.errors import InvariantViolation, ValidationError
from kise.shared_kernel.domain.identifiers import CategoryId, OwnerId
from kise.shared_kernel.domain.money import Money

OWNER = OwnerId.new()
CATEGORY = CategoryId.new()


def an_expense(**overrides) -> Expense:
    kwargs = {
        "owner_id": OWNER,
        "category_id": CATEGORY,
        "amount": Money.from_major("120.50"),
        "spent_on": SpendDate.from_ethiopian(2018, 11, 15),
    }
    kwargs.update(overrides)
    return Expense.record(**kwargs)


def test_recording_announces_itself():
    expense = an_expense()
    events = expense.pull_events()
    assert [e.name for e in events] == ["ExpenseRecorded"]
    assert events[0].amount == Money.from_major("120.50")
    assert events[0].spent_on == date(2026, 7, 22)


def test_amount_must_be_positive():
    with pytest.raises(InvariantViolation):
        an_expense(amount=Money.zero())
    with pytest.raises(InvariantViolation):
        an_expense(amount=Money(-1))


def test_amount_must_be_money_not_a_number():
    with pytest.raises(ValidationError):
        an_expense(amount=120)


def test_the_entry_calendar_is_remembered_but_storage_is_gregorian():
    """FR-2.4 and FR-4.2: type it in ሐምሌ, store 22 July 2026, read it back either way."""
    expense = an_expense()
    assert expense.spent_on.gregorian == date(2026, 7, 22)
    assert expense.spent_on.entered_in is CalendarKind.ETHIOPIAN
    assert expense.spent_on.ethiopian.iso == "2018-11-15"


def test_falls_in_period_for_both_calendars():
    expense = an_expense()
    assert expense.falls_in(Period(CalendarKind.ETHIOPIAN, 2018, 11))
    assert expense.falls_in(Period(CalendarKind.GREGORIAN, 2026, 7))
    assert not expense.falls_in(Period(CalendarKind.ETHIOPIAN, 2018, 12))
    assert expense.period(CalendarKind.ETHIOPIAN) == Period(CalendarKind.ETHIOPIAN, 2018, 11)


def test_note_is_bounded_and_blank_becomes_none():
    assert an_expense(note="   ").note is None
    assert an_expense(note="  Taxi to Bole  ").note == "Taxi to Bole"
    with pytest.raises(ValidationError):
        an_expense(note="x" * 501)


def test_payment_method_defaults_to_cash_and_accepts_telebirr():
    assert an_expense().payment_method is PaymentMethod.CASH
    assert an_expense(payment_method="telebirr").payment_method is PaymentMethod.TELEBIRR
    with pytest.raises(ValidationError):
        an_expense(payment_method="bitcoin")


def test_edits():
    expense = an_expense()
    expense.change_amount(Money.from_major("200"))
    assert expense.amount == Money.from_major("200")

    other_category = CategoryId.new()
    expense.recategorise(other_category)
    assert expense.category_id == other_category

    expense.move_to(SpendDate.from_gregorian(date(2026, 8, 1)))
    assert expense.spent_on.gregorian == date(2026, 8, 1)
    assert expense.spent_on.entered_in is CalendarKind.GREGORIAN

    expense.change_payment_method("bank")
    assert expense.payment_method is PaymentMethod.BANK


def test_amount_cannot_change_currency_or_become_zero():
    expense = an_expense()
    with pytest.raises(InvariantViolation):
        expense.change_amount(Money.from_major("10", "USD"))
    with pytest.raises(InvariantViolation):
        expense.change_amount(Money.zero())


def test_move_to_requires_a_spend_date():
    with pytest.raises(ValidationError):
        an_expense().move_to(date(2026, 8, 1))
