# Kise backend image.
#
# A small, reproducible image: install the pinned lock file first (so the dependency layer is cached
# across code changes), then the package itself. The landing page's stylesheet (static/styles/app.css)
# is compiled by `make web-css` and committed, so the image needs no Node stage. Runs as a non-root user
# and serves with uvicorn.
FROM python:3.13-slim AS base

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app

# System deps: libpq for psycopg's binary wheel is bundled, so only curl is added for the healthcheck.
RUN apt-get update \
    && apt-get install -y --no-install-recommends curl \
    && rm -rf /var/lib/apt/lists/*

# Dependencies first, from the fully resolved lock file, for layer caching. Dev deps (pytest, ruff,
# httpx) are included so the same image runs `make test` / `make lint` through compose, not just the
# server. It is the one environment for every task.
COPY requirements-dev.txt ./
RUN pip install -r requirements-dev.txt

# Then the application.
COPY pyproject.toml ./
COPY src ./src
COPY migrations ./migrations
COPY alembic.ini ./
COPY tests ./tests
RUN pip install --no-deps -e .

# The landing page: template, favicon and the compiled stylesheet under static/styles/.
COPY templates ./templates
COPY static ./static

# Drop privileges.
RUN useradd --create-home --uid 1000 kise
USER kise

EXPOSE 8000

# The compose file runs migrations before this; on its own the image just serves.
CMD ["uvicorn", "kise.platform.api.app:app", "--host", "0.0.0.0", "--port", "8000"]
