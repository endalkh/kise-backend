"""Wire schemas for categories and expenses, and the mapping to and from the application layer.

The shapes here honour the design's contract:

* Money goes out as ``{"amount_minor": 12345, "currency": "ETB"}`` — integer minor units, never a
  float, matching the Dart ``Money.fromJson`` on the client which reads ``amount_minor``.
* Every date goes out in both calendars, via ``SpendDate.describe()``; it comes in as a
  ``{"calendar", "value"}`` pair, via the shared ``DateInputSchema``.

As everywhere in presentation, Pydantic stops at this file: a request becomes an application
command, a view becomes a response model. Category/Expense ids arrive as strings and are parsed
into typed ids by the router before the command is built.
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field

from kise.expense_tracking.application.commands import (
    CreateCategoryCommand,
    ItemLineInput,
    RecordExpenseCommand,
    UpdateCategoryCommand,
    UpdateExpenseCommand,
)
from kise.expense_tracking.application.views import CategoryView, ExpensePage, ExpenseView
from kise.platform.api.schemas import DateInputSchema
from kise.shared_kernel.domain.identifiers import CategoryId, ExpenseId, ItemId, OwnerId, UnitId
from kise.shared_kernel.domain.money import Money


class MoneyView(BaseModel):
    """Money on the wire: integer minor units plus currency. Never a float."""

    amount_minor: int
    currency: str

    @classmethod
    def of(cls, money: Money) -> MoneyView:
        return cls(amount_minor=money.minor_units, currency=money.currency)


# -- categories ---------------------------------------------------------


class CreateCategoryRequest(BaseModel):
    name: str = Field(min_length=1, max_length=80)
    name_am: str | None = Field(default=None, max_length=80)
    color: str | None = Field(default=None, examples=["#F59E0B"])
    icon: str | None = Field(default=None, examples=["coffee"])

    def to_command(self, owner_id: OwnerId) -> CreateCategoryCommand:
        return CreateCategoryCommand(
            owner_id=owner_id,
            name=self.name,
            name_am=self.name_am,
            color=self.color,
            icon=self.icon,
        )


class UpdateCategoryRequest(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=80)
    name_am: str | None = Field(default=None, max_length=80)
    color: str | None = None
    icon: str | None = None

    def to_command(self, owner_id: OwnerId, category_id: CategoryId) -> UpdateCategoryCommand:
        return UpdateCategoryCommand(
            owner_id=owner_id,
            category_id=category_id,
            name=self.name,
            name_am=self.name_am,
            color=self.color,
            icon=self.icon,
        )


class CategoryResponse(BaseModel):
    id: str
    name: str
    name_am: str | None
    color: str
    icon: str | None
    is_archived: bool
    is_default: bool

    @classmethod
    def of(cls, view: CategoryView) -> CategoryResponse:
        return cls(
            id=str(view.category_id),
            name=view.name,
            name_am=view.name_am,
            color=view.color,
            icon=view.icon,
            is_archived=view.is_archived,
            is_default=view.is_default,
        )


# -- expenses -----------------------------------------------------------


class ItemLineSchema(BaseModel):
    """The optional 'what was bought' part of an expense.

    Either an existing ``item_id`` or a new ``item_name`` to create on the fly, plus a decimal
    ``quantity`` string (e.g. ``"1.5"``) and the ``unit_id`` it is counted in.
    """

    item_id: str | None = None
    item_name: str | None = Field(default=None, max_length=60)
    item_name_am: str | None = Field(default=None, max_length=60)
    quantity: str | None = Field(default=None, examples=["1.5", "12"])
    unit_id: str | None = None

    def to_input(self) -> ItemLineInput:
        return ItemLineInput(
            item_id=ItemId.parse(self.item_id) if self.item_id else None,
            item_name=self.item_name,
            item_name_am=self.item_name_am,
            quantity=self.quantity,
            unit_id=UnitId.parse(self.unit_id) if self.unit_id else None,
        )


class RecordExpenseRequest(BaseModel):
    category_id: str
    amount_minor: int = Field(gt=0, description="Integer minor units, e.g. santim for ETB")
    spent_on: DateInputSchema
    note: str | None = Field(default=None, max_length=280)
    payment_method: str | None = None
    item: ItemLineSchema | None = None

    def to_command(self, owner_id: OwnerId) -> RecordExpenseCommand:
        return RecordExpenseCommand(
            owner_id=owner_id,
            category_id=CategoryId.parse(self.category_id),
            amount_minor=self.amount_minor,
            spent_on=self.spent_on.to_input(),
            note=self.note,
            payment_method=self.payment_method,
            item=self.item.to_input() if self.item else None,
        )


class UpdateExpenseRequest(BaseModel):
    category_id: str | None = None
    amount_minor: int | None = Field(default=None, gt=0)
    spent_on: DateInputSchema | None = None
    note: str | None = Field(default=None, max_length=280)
    payment_method: str | None = None
    item: ItemLineSchema | None = None
    clear_item: bool = False

    def to_command(self, owner_id: OwnerId, expense_id: ExpenseId) -> UpdateExpenseCommand:
        return UpdateExpenseCommand(
            owner_id=owner_id,
            expense_id=expense_id,
            category_id=(
                CategoryId.parse(self.category_id) if self.category_id is not None else None
            ),
            amount_minor=self.amount_minor,
            spent_on=self.spent_on.to_input() if self.spent_on is not None else None,
            note=self.note,
            payment_method=self.payment_method,
            item=self.item.to_input() if self.item else None,
            clear_item=self.clear_item,
        )


class ItemLineView(BaseModel):
    """The item line on an expense response: what, how much, in what unit — null when absent."""

    item_id: str
    item_name: str | None
    item_name_am: str | None
    quantity: str  # decimal string, e.g. "1.5"
    quantity_milli: int  # integer thousandths, for exact client-side arithmetic
    unit_id: str
    unit_code: str | None
    unit_name: str | None
    unit_name_am: str | None


class ExpenseResponse(BaseModel):
    id: str
    category_id: str
    amount: MoneyView
    spent_on: dict[str, Any]  # SpendDate.describe(): both calendars at once
    note: str | None
    payment_method: str
    category_name: str | None
    category_name_am: str | None
    item: ItemLineView | None = None

    @classmethod
    def of(cls, view: ExpenseView) -> ExpenseResponse:
        item: ItemLineView | None = None
        if view.item_id is not None and view.quantity is not None and view.unit_id is not None:
            item = ItemLineView(
                item_id=str(view.item_id),
                item_name=view.item_name,
                item_name_am=view.item_name_am,
                quantity=view.quantity.format(),
                quantity_milli=view.quantity.milli,
                unit_id=str(view.unit_id),
                unit_code=view.unit_code,
                unit_name=view.unit_name,
                unit_name_am=view.unit_name_am,
            )
        return cls(
            id=str(view.expense_id),
            category_id=str(view.category_id),
            amount=MoneyView.of(view.amount),
            spent_on=view.spent_on.describe(),
            note=view.note,
            payment_method=view.payment_method,
            category_name=view.category_name,
            category_name_am=view.category_name_am,
            item=item,
        )


class ExpensePageResponse(BaseModel):
    """A page of expenses with paging metadata and the page total, as the app shows it."""

    items: list[ExpenseResponse]
    total: int
    limit: int
    offset: int
    total_amount: MoneyView

    @classmethod
    def of(cls, page: ExpensePage) -> ExpensePageResponse:
        return cls(
            items=[ExpenseResponse.of(item) for item in page.items],
            total=page.total,
            limit=page.limit,
            offset=page.offset,
            total_amount=MoneyView.of(page.total_amount),
        )
