import pytest

from kise.expense_tracking.domain.errors import (
    CategoryArchived,
    CategoryNameTaken,
    NotOwned,
)
from kise.expense_tracking.domain.models import (
    DEFAULT_CATEGORIES,
    Category,
    default_categories_for,
)
from kise.expense_tracking.domain.policies import (
    ensure_category_usable,
    ensure_name_is_free,
    ensure_owned_by,
)
from kise.expense_tracking.domain.value_objects import Color
from kise.shared_kernel.domain.errors import ValidationError
from kise.shared_kernel.domain.identifiers import OwnerId

OWNER = OwnerId.new()


def a_category(**overrides) -> Category:
    kwargs = {"owner_id": OWNER, "name": "Transport", "name_am": "ትራንስፖርት"}
    kwargs.update(overrides)
    return Category.create(**kwargs)


def test_name_is_trimmed_and_required():
    assert a_category(name="  Coffee   money ").name == "Coffee money"
    with pytest.raises(ValidationError):
        a_category(name="   ")
    with pytest.raises(ValidationError):
        a_category(name="x" * 61)


def test_label_prefers_amharic_when_asked():
    category = a_category()
    assert category.label("am") == "ትራንስፖርት"
    assert category.label("en") == "Transport"
    # Falls back to the name when there is no Amharic label.
    assert a_category(name_am=None).label("am") == "Transport"


def test_colour_must_be_a_hex_triplet():
    assert a_category(color="#e53935").color == Color("#E53935")
    with pytest.raises(ValidationError):
        a_category(color="red")
    with pytest.raises(ValidationError):
        a_category(color="#FFF")


def test_archived_categories_are_read_only_but_still_explain_history():
    category = a_category()
    category.archive()
    assert category.is_archived
    assert category.name == "Transport"  # old expenses still make sense
    with pytest.raises(CategoryArchived):
        category.rename("Taxi")
    with pytest.raises(CategoryArchived):
        category.recolor("#000000")
    with pytest.raises(CategoryArchived):
        category.archive()
    category.restore()
    category.rename("Taxi", "ታክሲ")
    assert (category.name, category.name_am) == ("Taxi", "ታክሲ")


def test_new_spending_cannot_use_an_archived_category():
    category = a_category()
    ensure_category_usable(category)  # live: fine
    category.archive()
    with pytest.raises(CategoryArchived):
        ensure_category_usable(category)


def test_comparison_key_is_case_insensitive():
    assert a_category(name="Transport").comparison_key == "transport"


def test_name_uniqueness_policy():
    existing = [a_category(name="Food"), a_category(name="Transport")]
    ensure_name_is_free("Health", existing=existing)
    with pytest.raises(CategoryNameTaken):
        ensure_name_is_free("food", existing=existing)
    with pytest.raises(CategoryNameTaken):
        ensure_name_is_free("  FOOD ", existing=existing)


def test_name_uniqueness_policy_ignores_the_category_being_renamed():
    food = a_category(name="Food")
    existing = [food, a_category(name="Transport")]
    # Re-saving Food under a differently-cased version of its own name is allowed.
    ensure_name_is_free("FOOD", existing=existing, ignoring=food.id)
    with pytest.raises(CategoryNameTaken):
        ensure_name_is_free("Transport", existing=existing, ignoring=food.id)


def test_ownership_policy():
    ensure_owned_by(OWNER, a_category())
    with pytest.raises(NotOwned):
        ensure_owned_by(OwnerId.new(), a_category())
    with pytest.raises(NotOwned):
        ensure_owned_by(OWNER, object())


def test_default_categories_are_bilingual_and_marked():
    categories = default_categories_for(OWNER)
    assert len(categories) == len(DEFAULT_CATEGORIES) == 10
    assert all(c.is_default for c in categories)
    assert all(c.owner_id == OWNER for c in categories)
    assert all(c.name_am for c in categories)
    names = {c.name for c in categories}
    assert {"Food", "Transport", "Rent", "Savings", "Other"} <= names
    # No duplicates, so the uniqueness policy cannot trip on the seed itself.
    assert len({c.comparison_key for c in categories}) == 10
    amharic = {c.name: c.name_am for c in categories}
    assert amharic["Food"] == "ምግብ"
    assert amharic["Rent"] == "ቤት ኪራይ"
