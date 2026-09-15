"""Events published by the Expense Tracking context.

Only ``OwnerRegistered`` has a subscriber in v1; these exist because they are part of the language
of the domain and because reminders are the first thing v2 will need.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date

from kise.shared_kernel.domain.events import DomainEvent
from kise.shared_kernel.domain.identifiers import (
    CategoryId,
    ExpenseId,
    FixedExpenseId,
    OwnerId,
)
from kise.shared_kernel.domain.money import Money


@dataclass(frozen=True, slots=True, kw_only=True)
class ExpenseRecorded(DomainEvent):
    expense_id: ExpenseId
    owner_id: OwnerId
    category_id: CategoryId
    amount: Money
    spent_on: date


@dataclass(frozen=True, slots=True, kw_only=True)
class FixedExpenseScheduled(DomainEvent):
    fixed_expense_id: FixedExpenseId
    owner_id: OwnerId
    title: str
    amount: Money
    anchor_calendar: str
    start_period: str


@dataclass(frozen=True, slots=True, kw_only=True)
class OccurrenceSettled(DomainEvent):
    fixed_expense_id: FixedExpenseId
    owner_id: OwnerId
    period: str
    amount: Money
    settled_on: date
