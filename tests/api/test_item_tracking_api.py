"""The item-tracking API, end to end: units, items, item-line expenses, and the usage report.

These drive real HTTP through the TestClient against an in-memory SQLite database, exercising the
routers, the item-line resolution in the expense service, and the month-end aggregation. What they
prove:

* the default units are seeded and listable, and an admin can add a custom one;
* an expense can carry an item — chosen by id or created on the fly by name — with a quantity in a
  unit, and it comes back on the response;
* the month-end report groups usage by (item, unit), summing quantity and money, so two sugar
  purchases become "15 kg";
* quantity survives the wire exactly, as both a decimal string and integer thousandths.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from kise.platform.api.app import create_app
from kise.platform.config import Settings
from kise.platform.container import Container

SECRET = "a-secret-long-enough-to-be-taken-seriously-xxxx"


@pytest.fixture
def client() -> TestClient:
    settings = Settings(database_url="sqlite://", secret_key=SECRET, default_currency="ETB")
    container = Container(settings)
    container.create_schema()
    container.seed_units()
    return TestClient(create_app(settings, container=container))


def signed_in(client: TestClient, email: str = "abebe@example.com") -> dict[str, str]:
    body = {
        "email": email,
        "password": "correct horse battery",
        "display_name": "Abebe",
        "calendar": "ethiopian",
        "language": "am",
    }
    token = client.post("/api/auth/register", json=body).json()["token"]
    return {"Authorization": f"Bearer {token}"}


def first_category_id(client: TestClient, header: dict[str, str]) -> str:
    return client.get("/api/categories", headers=header).json()[0]["id"]


def unit_by_code(client: TestClient, header: dict[str, str], code: str) -> dict:
    units = client.get("/api/units", headers=header).json()
    return next(u for u in units if u["code"] == code)


# -- units --------------------------------------------------------------


def test_default_units_are_seeded(client: TestClient):
    header = signed_in(client)
    units = client.get("/api/units", headers=header).json()
    codes = {u["code"] for u in units}
    assert {"kg", "g", "l", "ml", "pcs"} <= codes
    assert all(u["is_system"] for u in units)
    # Amharic labels are present.
    kg = next(u for u in units if u["code"] == "kg")
    assert kg["name_am"] == "ኪሎግራም"


def test_units_require_authentication(client: TestClient):
    assert client.get("/api/units").status_code == 401


def test_admin_can_add_a_custom_unit(client: TestClient):
    header = signed_in(client)
    response = client.post(
        "/api/units",
        headers=header,
        json={"code": "crate", "name": "Crate", "name_am": "ሳጥን"},
    )
    assert response.status_code == 201, response.text
    body = response.json()
    assert body["code"] == "crate"
    assert body["is_system"] is False


def test_duplicate_unit_code_is_409(client: TestClient):
    header = signed_in(client)
    client.post("/api/units", headers=header, json={"code": "crate", "name": "Crate"})
    dup = client.post("/api/units", headers=header, json={"code": "crate", "name": "Crate 2"})
    assert dup.status_code == 409
    assert dup.json()["code"] == "unit_code_taken"


# -- items --------------------------------------------------------------


def test_create_and_list_items(client: TestClient):
    header = signed_in(client)
    kg = unit_by_code(client, header, "kg")
    created = client.post(
        "/api/items",
        headers=header,
        json={"name": "Sugar", "name_am": "ስኳር", "default_unit_id": kg["id"]},
    )
    assert created.status_code == 201, created.text
    assert created.json()["name"] == "Sugar"
    assert created.json()["default_unit_id"] == kg["id"]

    items = client.get("/api/items", headers=header).json()
    assert [i["name"] for i in items] == ["Sugar"]


def test_duplicate_item_name_is_409(client: TestClient):
    header = signed_in(client)
    client.post("/api/items", headers=header, json={"name": "Sugar"})
    dup = client.post("/api/items", headers=header, json={"name": "sugar"})  # case-insensitive
    assert dup.status_code == 409
    assert dup.json()["code"] == "item_name_taken"


# -- item-line expenses -------------------------------------------------


def test_record_expense_with_a_new_item_by_name(client: TestClient):
    header = signed_in(client)
    category_id = first_category_id(client, header)
    kg = unit_by_code(client, header, "kg")

    response = client.post(
        "/api/expenses",
        headers=header,
        json={
            "category_id": category_id,
            "amount_minor": 48000,
            "spent_on": {"calendar": "gregorian", "value": "2026-09-01"},
            "item": {
                "item_name": "Sugar",
                "item_name_am": "ስኳር",
                "quantity": "12",
                "unit_id": kg["id"],
            },
        },
    )
    assert response.status_code == 201, response.text
    item = response.json()["item"]
    assert item is not None
    assert item["item_name"] == "Sugar"
    assert item["quantity"] == "12"
    assert item["quantity_milli"] == 12000
    assert item["unit_code"] == "kg"

    # The item now exists in the owner's list (created on the fly).
    items = client.get("/api/items", headers=header).json()
    assert any(i["name"] == "Sugar" for i in items)


def test_record_expense_with_an_existing_item(client: TestClient):
    header = signed_in(client)
    category_id = first_category_id(client, header)
    litre = unit_by_code(client, header, "l")
    item = client.post("/api/items", headers=header, json={"name": "Oil"}).json()

    response = client.post(
        "/api/expenses",
        headers=header,
        json={
            "category_id": category_id,
            "amount_minor": 64000,
            "spent_on": {"calendar": "gregorian", "value": "2026-09-02"},
            "item": {"item_id": item["id"], "quantity": "8", "unit_id": litre["id"]},
        },
    )
    assert response.status_code == 201, response.text
    assert response.json()["item"]["item_id"] == item["id"]
    assert response.json()["item"]["unit_code"] == "l"


def test_fractional_quantity_survives_the_wire(client: TestClient):
    header = signed_in(client)
    category_id = first_category_id(client, header)
    kg = unit_by_code(client, header, "kg")
    response = client.post(
        "/api/expenses",
        headers=header,
        json={
            "category_id": category_id,
            "amount_minor": 6000,
            "spent_on": {"calendar": "gregorian", "value": "2026-09-03"},
            "item": {"item_name": "Onion", "quantity": "1.5", "unit_id": kg["id"]},
        },
    )
    assert response.status_code == 201, response.text
    assert response.json()["item"]["quantity"] == "1.5"
    assert response.json()["item"]["quantity_milli"] == 1500


def test_an_amount_only_expense_still_works(client: TestClient):
    header = signed_in(client)
    category_id = first_category_id(client, header)
    response = client.post(
        "/api/expenses",
        headers=header,
        json={
            "category_id": category_id,
            "amount_minor": 2000,
            "spent_on": {"calendar": "gregorian", "value": "2026-09-04"},
        },
    )
    assert response.status_code == 201, response.text
    assert response.json()["item"] is None


# -- the month-end report ----------------------------------------------


def test_item_usage_report_aggregates_by_item_and_unit(client: TestClient):
    header = signed_in(client)
    category_id = first_category_id(client, header)
    kg = unit_by_code(client, header, "kg")
    litre = unit_by_code(client, header, "l")

    def record(name: str, qty: str, unit_id: str, amount: int) -> None:
        r = client.post(
            "/api/expenses",
            headers=header,
            json={
                "category_id": category_id,
                "amount_minor": amount,
                "spent_on": {"calendar": "gregorian", "value": "2026-09-10"},
                "item": {"item_name": name, "quantity": qty, "unit_id": unit_id},
            },
        )
        assert r.status_code == 201, r.text

    record("Sugar", "12", kg["id"], 48000)
    record("Sugar", "3", kg["id"], 12000)  # same item + unit -> should sum to 15 kg
    record("Oil", "8", litre["id"], 64000)

    report = client.get(
        "/api/reports/item-usage",
        headers=header,
        params={"period_year": 2026, "period_month": 9, "period_calendar": "gregorian"},
    )
    assert report.status_code == 200, report.text
    body = report.json()
    assert body["currency"] == "ETB"
    lines = {line["item_name"]: line for line in body["lines"]}
    assert lines["Sugar"]["total_quantity"] == "15"
    assert lines["Sugar"]["total_quantity_milli"] == 15000
    assert lines["Sugar"]["unit_code"] == "kg"
    assert lines["Sugar"]["entry_count"] == 2
    assert lines["Oil"]["total_quantity"] == "8"
    assert lines["Oil"]["total_amount"] == {"amount_minor": 64000, "currency": "ETB"}
    # Sorted by spend, so Oil (640) leads Sugar (600).
    assert [line["item_name"] for line in body["lines"]] == ["Oil", "Sugar"]


def test_item_usage_report_is_empty_for_a_quiet_month(client: TestClient):
    header = signed_in(client)
    report = client.get(
        "/api/reports/item-usage",
        headers=header,
        params={"period_year": 2030, "period_month": 1, "period_calendar": "gregorian"},
    )
    assert report.status_code == 200
    assert report.json()["lines"] == []
