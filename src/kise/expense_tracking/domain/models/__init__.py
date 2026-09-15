"""Domain models of the Expense Tracking context — the core domain, one import point.

The split behind this facade:

``entities/``       identity by id, mutable: ``Category``, ``Expense``, ``FixedExpense``,
                    ``Settlement``, ``Item``, ``UnitOfMeasurement``
``value_objects/``  compared by value, immutable: ``Occurrence``, ``Color``, ``PaymentMethod``,
                    ``Quantity``

Not to be confused with this context's ``infrastructure/persistence/models.py``, which holds the
database tables. These classes know nothing about SQLAlchemy; mappers translate between the two.
"""

from kise.expense_tracking.domain.entities import (
    DEFAULT_CATEGORIES,
    DEFAULT_UNITS,
    Category,
    Expense,
    FixedExpense,
    Item,
    Settlement,
    UnitOfMeasurement,
    default_categories_for,
    default_units,
)
from kise.expense_tracking.domain.value_objects import (
    MAX_DUE_DAY,
    Color,
    DueDay,
    Occurrence,
    PaymentMethod,
    Quantity,
)

__all__ = [
    "DEFAULT_CATEGORIES",
    "DEFAULT_UNITS",
    "MAX_DUE_DAY",
    "Category",
    "Color",
    "DueDay",
    "Expense",
    "FixedExpense",
    "Item",
    "Occurrence",
    "PaymentMethod",
    "Quantity",
    "Settlement",
    "UnitOfMeasurement",
    "default_categories_for",
    "default_units",
]
