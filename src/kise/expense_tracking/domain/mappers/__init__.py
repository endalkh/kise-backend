"""Mapping contracts for the Expense Tracking context.

Ports, not implementations: the specification of how each aggregate is translated to and from
storage. The SQLAlchemy that does it lives in
``expense_tracking/infrastructure/persistence/mappers.py``, and a contract test asserts each
implementation satisfies the protocol declared here — so these cannot rot into documentation.

One contract per **aggregate root**, never per table: ``Settlement`` has none, because it is only
ever persisted through its ``FixedExpense``.
"""

from kise.expense_tracking.domain.mappers.category_mapping import CategoryMapping
from kise.expense_tracking.domain.mappers.expense_mapping import ExpenseMapping
from kise.expense_tracking.domain.mappers.fixed_expense_mapping import FixedExpenseMapping

__all__ = ["CategoryMapping", "ExpenseMapping", "FixedExpenseMapping"]
