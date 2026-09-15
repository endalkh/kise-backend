"""Entities of the Expense Tracking context — identity by id, mutable, rule-carrying.

Aggregate roots: ``Category``, ``Expense``, ``FixedExpense``, ``Item``, ``UnitOfMeasurement``.
``Settlement`` is a child entity, reachable only through its ``FixedExpense`` root, which is what
makes "at most one Settlement per Period" enforceable.
"""

from kise.expense_tracking.domain.entities.category import (
    DEFAULT_CATEGORIES,
    Category,
    default_categories_for,
)
from kise.expense_tracking.domain.entities.expense import Expense
from kise.expense_tracking.domain.entities.fixed_expense import FixedExpense, Settlement
from kise.expense_tracking.domain.entities.item import Item
from kise.expense_tracking.domain.entities.unit_of_measurement import (
    DEFAULT_UNITS,
    UnitOfMeasurement,
    default_units,
)

__all__ = [
    "DEFAULT_CATEGORIES",
    "DEFAULT_UNITS",
    "Category",
    "Expense",
    "FixedExpense",
    "Item",
    "Settlement",
    "UnitOfMeasurement",
    "default_categories_for",
    "default_units",
]
