from datetime import UTC, datetime

import pytest

from kise.identity.domain.models import (
    EmailAddress,
    Owner,
    PasswordHash,
    Preferences,
)
from kise.shared_kernel.domain.calendar import CalendarKind, Language
from kise.shared_kernel.domain.errors import InvariantViolation, ValidationError

NOW = datetime(2026, 9, 4, 20, 0, tzinfo=UTC)
HASH = PasswordHash("$2b$12$fakefakefakefakefakefake")


def an_owner(**overrides) -> Owner:
    kwargs = {
        "email": EmailAddress("Selam@Example.com"),
        "password_hash": HASH,
        "display_name": "Selam Tesfaye",
        "registered_at": NOW,
    }
    kwargs.update(overrides)
    return Owner.register(**kwargs)


def test_registering_normalises_and_announces():
    owner = an_owner()
    assert str(owner.email) == "selam@example.com"
    assert owner.display_name == "Selam Tesfaye"
    events = owner.pull_events()
    assert [e.name for e in events] == ["OwnerRegistered"]
    assert events[0].owner_id == owner.id
    assert events[0].email == "selam@example.com"
    assert events[0].currency == "ETB"


def test_defaults_are_ethiopian_amharic_birr():
    """Kise is built for Ethiopian users first, so those are the defaults."""
    owner = an_owner()
    assert owner.preferences.calendar is CalendarKind.ETHIOPIAN
    assert owner.preferences.language is Language.AMHARIC
    assert owner.preferences.currency == "ETB"


@pytest.mark.parametrize(
    "bad", ["", "   ", "not-an-email", "no@domain", "two@@at.com", "spa ce@mail.com"]
)
def test_invalid_emails_are_rejected(bad):
    with pytest.raises(ValidationError):
        EmailAddress(bad)


def test_display_name_is_required_and_bounded():
    with pytest.raises(ValidationError):
        an_owner(display_name="  ")
    with pytest.raises(ValidationError):
        an_owner(display_name="x" * 61)
    assert an_owner(display_name="  Selam   Tesfaye ").display_name == "Selam Tesfaye"


def test_password_hash_never_renders_itself():
    assert "fake" not in repr(HASH)
    assert "fake" not in str(HASH)
    with pytest.raises(ValidationError):
        PasswordHash("")


def test_preferences_are_replaced_as_a_whole_or_one_at_a_time():
    owner = an_owner()
    owner.prefer_calendar("gregorian")
    assert owner.preferences.calendar is CalendarKind.GREGORIAN
    owner.prefer_language("en")
    assert owner.preferences.language is Language.ENGLISH
    owner.update_preferences(Preferences(calendar="ethiopian", language="am", currency="usd"))
    assert owner.preferences.currency == "USD"
    with pytest.raises(ValidationError):
        owner.update_preferences("gregorian")  # type: ignore[arg-type]


def test_unknown_calendar_or_language_is_rejected():
    with pytest.raises(ValidationError):
        Preferences(calendar="julian")
    with pytest.raises(ValidationError):
        Preferences(language="fr")
    with pytest.raises(ValidationError):
        Preferences(currency="BIRR")


def test_changing_password_requires_a_different_hash():
    owner = an_owner()
    with pytest.raises(InvariantViolation):
        owner.change_password(HASH)
    owner.change_password(PasswordHash("$2b$12$another"))
    assert owner.password_hash == PasswordHash("$2b$12$another")


def test_owner_identity_is_by_id():
    owner = an_owner()
    same = Owner(
        owner.id,
        email=EmailAddress("different@example.com"),
        password_hash=HASH,
        display_name="Different",
        preferences=Preferences(),
        registered_at=NOW,
    )
    assert owner == same
