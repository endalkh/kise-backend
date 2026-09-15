"""Shared wire schemas for the dual-calendar contract, plus the mappers to value objects.

The design fixes the wire format for dates and periods, and it is deliberately asymmetric:

* **In**, a date is a value plus the calendar it was written in — ``{"calendar": "ethiopian",
  "value": "2018-12-29"}`` — because the client types in one calendar and the server must not
  privilege either. A period is ``{"calendar": "ethiopian", "year": 2018, "month": 11}``.
* **Out**, a date is rendered in *both* calendars at once, so the app can show either without a
  round trip. That full rendering is produced by ``SpendDate.describe()`` and ``Period.labels()``;
  these schemas just declare the shape for the OpenAPI document.

Pydantic lives here, at the edge, and never reaches into the domain: a request model is turned into
a ``DateInput``/``PeriodInput`` (application command inputs) by an explicit ``to_input()``, and a
value object is turned into a response ``dict`` by ``describe()``/``labels()`` in the service views.
"""

from __future__ import annotations

from pydantic import BaseModel, Field

from kise.expense_tracking.application.commands import DateInput, PeriodInput


class DateInputSchema(BaseModel):
    """A date the client typed, plus the calendar it was written in."""

    value: str = Field(examples=["2026-09-04", "2018-12-29"])
    calendar: str = Field(default="gregorian", examples=["gregorian", "ethiopian"])

    def to_input(self) -> DateInput:
        return DateInput(value=self.value, calendar=self.calendar)


class PeriodInputSchema(BaseModel):
    """A month in a named calendar, as query/body input."""

    year: int = Field(ge=1, examples=[2018, 2026])
    month: int = Field(ge=1, le=13, examples=[11, 9])
    calendar: str = Field(default="ethiopian", examples=["ethiopian", "gregorian"])

    def to_input(self) -> PeriodInput:
        return PeriodInput(year=self.year, month=self.month, calendar=self.calendar)


class DateView(BaseModel):
    """A date rendered in both calendars, as every date goes out. Shape only — the values are

    produced by ``SpendDate.describe()``. Extra keys are allowed so the schema never has to chase
    the value object.
    """

    model_config = {"extra": "allow"}

    gregorian: str
    ethiopian: str
    ethiopian_month_name_am: str
    ethiopian_month_name_en: str
    entered_in: str


class PeriodView(BaseModel):
    """A period rendered with every label the client shows. Produced by ``Period.labels()``."""

    model_config = {"extra": "allow"}

    calendar: str
    label_am: str
    label_en: str
    first_day: str
    last_day: str
