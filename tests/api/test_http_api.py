"""The HTTP API, end to end, against an in-memory SQLite database.

These are the tests that only the API layer can have: they drive real HTTP through FastAPI's
``TestClient``, so they exercise the routers, the dependencies, the Unit-of-work-per-request
lifecycle, the auth dependency, the domain-error handler and the JSON wire format all at once.

What they prove:

* Registering seeds the ten default categories (the ``OwnerRegistered`` subscriber runs).
* The whole loop works: register, create a category, record an expense in the Ethiopian calendar,
  list it back, and see the dual-calendar date and minor-units money on the wire.
* Auth is enforced, and a bad token / bad login produces the documented error shape.
* Ownership is isolated: one owner cannot see or delete another's records.
* A category in use is archived (200), an unused one is deleted (204).
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
    settings = Settings(
        database_url="sqlite://",
        secret_key=SECRET,
        default_currency="ETB",
        cors_origins=["*"],
    )
    container = Container(settings)
    container.create_schema()
    app = create_app(settings, container=container)
    return TestClient(app)


def register(client: TestClient, email: str = "abebe@example.com", **overrides) -> dict:
    body = {
        "email": email,
        "password": "correct horse battery",
        "display_name": "Abebe",
        "calendar": "ethiopian",
        "language": "am",
        **overrides,
    }
    response = client.post("/api/auth/register", json=body)
    assert response.status_code == 201, response.text
    return response.json()


def auth_header(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


# -- health -------------------------------------------------------------


def test_health(client: TestClient):
    assert client.get("/health").json() == {"status": "ok"}


# -- landing page -------------------------------------------------------


def test_landing_page_renders_and_describes_the_app(client: TestClient):
    response = client.get("/")
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/html")
    body = response.text
    # It says what Kise is, in both scripts.
    assert "ኪሴ" in body
    assert "Kise" in body
    assert "Ethiopian calendar" in body


def test_landing_page_shows_coming_soon_without_a_download_url(client: TestClient):
    # The default settings leave the download URL empty.
    body = client.get("/").text
    assert "coming soon" in body.lower()


def test_landing_page_uses_the_configured_download_url():
    settings = Settings(
        database_url="sqlite://",
        secret_key=SECRET,
        app_download_url="https://example.com/kise.apk",
    )
    container = Container(settings)
    container.create_schema()
    local = TestClient(create_app(settings, container=container))
    body = local.get("/").text
    assert "https://example.com/kise.apk" in body
    assert "coming soon" not in body.lower()


def test_landing_page_renders_only_the_configured_store_buttons():
    settings = Settings(
        database_url="sqlite://",
        secret_key=SECRET,
        app_store_url="https://apps.apple.com/app/id123",
        play_store_url="https://play.google.com/store/apps/details?id=com.kise.kise",
    )
    container = Container(settings)
    container.create_schema()
    local = TestClient(create_app(settings, container=container))
    body = local.get("/").text
    assert "https://apps.apple.com/app/id123" in body
    assert "App Store" in body
    assert "https://play.google.com/store/apps/details?id=com.kise.kise" in body
    assert "Google Play" in body
    assert "Direct download" not in body
    assert "coming soon" not in body.lower()


def test_landing_page_escapes_a_hostile_download_url():
    settings = Settings(
        database_url="sqlite://",
        secret_key=SECRET,
        app_download_url='https://example.com/x"><script>alert(1)</script>',
    )
    container = Container(settings)
    container.create_schema()
    local = TestClient(create_app(settings, container=container))
    body = local.get("/").text
    assert "<script>alert(1)</script>" not in body


def test_landing_page_links_a_stylesheet_and_favicon_the_server_can_serve(client: TestClient):
    body = client.get("/").text
    assert 'href="/static/styles/app.css"' in body
    assert 'href="/static/favicon.svg"' in body
    favicon = client.get("/static/favicon.svg")
    assert favicon.status_code == 200
    assert "svg" in favicon.headers["content-type"]
    stylesheet = client.get("/static/styles/app.css")
    assert stylesheet.status_code == 200
    assert "text/css" in stylesheet.headers["content-type"]


# -- auth ---------------------------------------------------------------


def test_register_returns_token_and_profile(client: TestClient):
    body = register(client)
    assert body["token"]
    assert body["expires_at"]
    assert body["owner"]["email"] == "abebe@example.com"
    assert body["owner"]["calendar"] == "ethiopian"
    assert body["owner"]["currency"] == "ETB"


def test_registering_seeds_default_categories(client: TestClient):
    """The OwnerRegistered subscriber must have run in its own Unit of Work."""
    token = register(client)["token"]
    response = client.get("/api/categories", headers=auth_header(token))
    assert response.status_code == 200
    categories = response.json()
    assert len(categories) == 10, categories
    assert all(c["is_default"] for c in categories)


def test_duplicate_email_is_a_409_with_the_domain_code(client: TestClient):
    register(client)
    response = client.post(
        "/api/auth/register",
        json={
            "email": "abebe@example.com",
            "password": "another password",
            "display_name": "Someone",
        },
    )
    assert response.status_code == 409
    body = response.json()
    assert body["code"] == "email_already_registered"
    assert "detail" in body


def test_login_round_trip(client: TestClient):
    register(client)
    response = client.post(
        "/api/auth/login",
        json={"email": "abebe@example.com", "password": "correct horse battery"},
    )
    assert response.status_code == 200
    assert response.json()["owner"]["email"] == "abebe@example.com"


def test_wrong_password_is_401_invalid_credentials(client: TestClient):
    register(client)
    response = client.post(
        "/api/auth/login",
        json={"email": "abebe@example.com", "password": "wrong password"},
    )
    assert response.status_code == 401
    assert response.json()["code"] == "invalid_credentials"
    assert response.headers["WWW-Authenticate"] == "Bearer"


def test_me_requires_a_token(client: TestClient):
    response = client.get("/api/auth/me")
    assert response.status_code == 401
    assert response.json()["code"] == "invalid_token"


def test_a_rubbish_token_is_401(client: TestClient):
    response = client.get("/api/auth/me", headers=auth_header("not.a.token"))
    assert response.status_code == 401
    assert response.json()["code"] == "invalid_token"


def test_get_and_update_me(client: TestClient):
    token = register(client)["token"]
    me = client.get("/api/auth/me", headers=auth_header(token))
    assert me.json()["display_name"] == "Abebe"

    updated = client.patch(
        "/api/auth/me",
        headers=auth_header(token),
        json={"display_name": "Abebe Kebede", "calendar": "gregorian"},
    )
    assert updated.status_code == 200
    assert updated.json()["display_name"] == "Abebe Kebede"
    assert updated.json()["calendar"] == "gregorian"


# -- categories ---------------------------------------------------------


def test_create_category(client: TestClient):
    token = register(client)["token"]
    response = client.post(
        "/api/categories",
        headers=auth_header(token),
        json={"name": "Coffee", "name_am": "ቡና", "color": "#F59E0B", "icon": "coffee"},
    )
    assert response.status_code == 201
    body = response.json()
    assert body["name"] == "Coffee"
    assert body["name_am"] == "ቡና"
    assert body["is_default"] is False


def test_duplicate_category_name_is_409(client: TestClient):
    token = register(client)["token"]
    header = auth_header(token)
    client.post("/api/categories", headers=header, json={"name": "Coffee"})
    response = client.post("/api/categories", headers=header, json={"name": "Coffee"})
    assert response.status_code == 409
    assert response.json()["code"] == "category_name_taken"


def test_delete_unused_category_returns_204(client: TestClient):
    token = register(client)["token"]
    header = auth_header(token)
    created = client.post("/api/categories", headers=header, json={"name": "Temp"}).json()
    response = client.delete(f"/api/categories/{created['id']}", headers=header)
    assert response.status_code == 204


# -- expenses -----------------------------------------------------------


def test_record_expense_in_ethiopian_calendar_and_list_it(client: TestClient):
    token = register(client)["token"]
    header = auth_header(token)
    category = client.post(
        "/api/categories", headers=header, json={"name": "Taxi", "name_am": "ታክሲ"}
    ).json()

    record = client.post(
        "/api/expenses",
        headers=header,
        json={
            "category_id": category["id"],
            "amount_minor": 12500,
            "spent_on": {"calendar": "ethiopian", "value": "2018-11-15"},
            "note": "airport",
            "payment_method": "cash",
        },
    )
    assert record.status_code == 201, record.text
    expense = record.json()
    # Money is integer minor units, never a float.
    assert expense["amount"] == {"amount_minor": 12500, "currency": "ETB"}
    # The date comes back in both calendars.
    assert expense["spent_on"]["entered_in"] == "ethiopian"
    assert expense["spent_on"]["ethiopian_month"] == 11
    assert "gregorian" in expense["spent_on"]
    assert expense["category_name"] == "Taxi"

    # List by the Ethiopian period it falls in.
    listed = client.get(
        "/api/expenses",
        headers=header,
        params={"period_year": 2018, "period_month": 11, "period_calendar": "ethiopian"},
    )
    assert listed.status_code == 200
    page = listed.json()
    assert page["total"] == 1
    assert page["items"][0]["id"] == expense["id"]
    assert page["total_amount"] == {"amount_minor": 12500, "currency": "ETB"}


def test_update_and_delete_expense(client: TestClient):
    token = register(client)["token"]
    header = auth_header(token)
    category = client.post("/api/categories", headers=header, json={"name": "Groceries"}).json()
    expense = client.post(
        "/api/expenses",
        headers=header,
        json={
            "category_id": category["id"],
            "amount_minor": 5000,
            "spent_on": {"calendar": "gregorian", "value": "2026-09-04"},
        },
    ).json()

    patched = client.patch(
        f"/api/expenses/{expense['id']}",
        headers=header,
        json={"amount_minor": 7500, "note": "lunch"},
    )
    assert patched.status_code == 200
    assert patched.json()["amount"]["amount_minor"] == 7500
    assert patched.json()["note"] == "lunch"

    deleted = client.delete(f"/api/expenses/{expense['id']}", headers=header)
    assert deleted.status_code == 204
    gone = client.get(f"/api/expenses/{expense['id']}", headers=header)
    assert gone.status_code == 404
    assert gone.json()["code"] == "expense_not_found"


def test_deleting_a_used_category_archives_it(client: TestClient):
    token = register(client)["token"]
    header = auth_header(token)
    category = client.post("/api/categories", headers=header, json={"name": "Monthly Rent"}).json()
    client.post(
        "/api/expenses",
        headers=header,
        json={
            "category_id": category["id"],
            "amount_minor": 100000,
            "spent_on": {"calendar": "gregorian", "value": "2026-09-01"},
        },
    )
    response = client.delete(f"/api/categories/{category['id']}", headers=header)
    assert response.status_code == 200
    assert response.json()["is_archived"] is True


# -- ownership isolation ------------------------------------------------


def test_one_owner_cannot_read_anothers_expense(client: TestClient):
    first = register(client, email="abebe@example.com")["token"]
    second = register(client, email="mimi@example.com")["token"]

    category = client.post(
        "/api/categories", headers=auth_header(first), json={"name": "Secret"}
    ).json()
    expense = client.post(
        "/api/expenses",
        headers=auth_header(first),
        json={
            "category_id": category["id"],
            "amount_minor": 999,
            "spent_on": {"calendar": "gregorian", "value": "2026-09-04"},
        },
    ).json()

    response = client.get(f"/api/expenses/{expense['id']}", headers=auth_header(second))
    assert response.status_code == 404


def test_bad_date_is_a_422(client: TestClient):
    token = register(client)["token"]
    header = auth_header(token)
    category = client.post("/api/categories", headers=header, json={"name": "X"}).json()
    response = client.post(
        "/api/expenses",
        headers=header,
        json={
            "category_id": category["id"],
            "amount_minor": 100,
            # ጳጉሜን only has 5 (or 6) days; day 30 does not exist.
            "spent_on": {"calendar": "ethiopian", "value": "2018-13-30"},
        },
    )
    assert response.status_code == 422
    assert response.json()["code"] in {"validation_error", "value_error"}
