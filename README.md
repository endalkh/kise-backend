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

## Deployment (Heroku via GitHub)

Pushes to `main` deploy automatically: `.github/workflows/deploy-heroku.yml` runs lint and the test
suite, then pushes to Heroku's git remote. The `Procfile`'s `release` phase applies migrations
(`alembic upgrade head`) before the new dynos take traffic, and the workflow polls `/health`
afterwards so a broken release fails the run. `.github/workflows/ci.yml` covers pull requests.

One-time setup:

```bash
heroku create <app>
heroku addons:create heroku-postgresql:essential-0 --app <app>

# A root package.json makes Heroku detect Node first — pin the Python buildpack explicitly.
heroku buildpacks:set heroku/python --app <app>

heroku config:set KISE_SECRET_KEY="$(python3 -c 'import secrets; print(secrets.token_urlsafe(48))')" \
                  KISE_DEFAULT_CURRENCY=ETB \
                  KISE_CORS_ORIGINS='["https://your-frontend"]' --app <app>
```

Then, in GitHub under *Settings → Secrets and variables → Actions*:

| kind     | name              | value                                             |
| -------- | ----------------- | ------------------------------------------------- |
| secret   | `HEROKU_API_KEY`  | output of `heroku authorizations:create`          |
| variable | `HEROKU_APP_NAME` | the Heroku app name                               |

`DATABASE_URL` needs no configuration: the Postgres add-on exports it and `platform/config.py`
adopts it, rewriting `postgres://` to `postgresql+psycopg://`. Nothing else is required — but do
narrow `KISE_CORS_ORIGINS` from the `["*"]` default, and note that `KISE_SECRET_KEY` must be set or
the app boots with the insecure placeholder.

`make deploy` pushes manually (bypassing CI) if you need an escape hatch, and `heroku.yml` is
included for a container deploy (`heroku stack:set container`) using the repository `Dockerfile`,
which is the more reliable path if buildpack detection ever gets in the way.
