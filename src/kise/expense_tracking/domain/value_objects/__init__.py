"""Value objects of the Expense Tracking context — compared by value, immutable.

``Occurrence`` is the notable one: a Fixed Monthly Expense projected into one Period, computed on
demand and never stored.
"""

from kise.expense_tracking.domain.value_objects.due_day import MAX_DUE_DAY, DueDay
from kise.expense_tracking.domain.value_objects.occurrence import Occurrence
from kise.expense_tracking.domain.value_objects.quantity import Quantity
from kise.expense_tracking.domain.value_objects.values import (
    MAX_CATEGORY_NAME_LENGTH,
    MAX_ICON_LENGTH,
    MAX_NOTE_LENGTH,
    MAX_TITLE_LENGTH,
    Color,
    PaymentMethod,
    clean_note,
    clean_optional_text,
    clean_required_text,
)

__all__ = [
    "MAX_DUE_DAY",
    "DueDay",
    "MAX_CATEGORY_NAME_LENGTH",
    "MAX_ICON_LENGTH",
    "MAX_NOTE_LENGTH",
    "MAX_TITLE_LENGTH",
    "Color",
    "Occurrence",
    "PaymentMethod",
    "Quantity",
    "clean_note",
    "clean_optional_text",
    "clean_required_text",
]
