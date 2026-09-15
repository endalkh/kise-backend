# kise-backend

FastAPI backend for **Kise**, a personal expense tracker for Ethiopian users. Domain-driven,
PostgreSQL-backed, with the Ethiopian calendar (Amharic month names) as a first-class citizen
alongside the Gregorian one.

The Flutter mobile client lives in a separate repository: **kise-app**.

## Running

Requires Python 3.11+ ([uv](https://docs.astral.sh/uv/) recommended). Developed on 3.13.

```bash
uv venv --python 3.13
uv pip install -e ".[dev]"          # or: uv pip install -r requirements-dev.txt

cp .env.example .env                # then change KISE_SECRET_KEY

.venv/bin/alembic upgrade head      # create the schema
.venv/bin/uvicorn kise.platform.api.app:app --reload
```

- `http://127.0.0.1:8000/`        landing page
- `http://127.0.0.1:8000/docs`    interactive API (Swagger)
- `http://127.0.0.1:8000/health`  health check

Configuration is read from the environment with a `KISE_` prefix: `KISE_DATABASE_URL`,
`KISE_SECRET_KEY`, `KISE_ACCESS_TOKEN_EXPIRE_MINUTES`, `KISE_DEFAULT_CURRENCY`, `KISE_CORS_ORIGINS`.
A platform-provided `DATABASE_URL` (e.g. from Heroku) is adopted automatically when
`KISE_DATABASE_URL` is unset, and a bare `postgres://` scheme is normalised to `postgresql+psycopg://`.

## Docker

```bash
docker compose up --build           # Postgres + backend (migrates, then serves)
```

## Testing

```bash
.venv/bin/python -m pytest -q
.venv/bin/ruff check src tests migrations
```
