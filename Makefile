# Kise backend — common development tasks.
# Run `make help` to list available targets.

VENV    := .venv
BIN     := $(VENV)/bin
PYTHON  := $(BIN)/python
PYTEST  := $(BIN)/pytest
RUFF    := $(BIN)/ruff
ALEMBIC := $(BIN)/alembic
UVICORN := $(BIN)/uvicorn

APP     := kise.platform.api.app:app
SRC     := src tests migrations

.DEFAULT_GOAL := help

.PHONY: help venv install env run migrate revision downgrade \
        test lint format check css css-watch \
        up up-d down logs build clean

help: ## Show this help
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) \
		| sort \
		| awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-14s\033[0m %s\n", $$1, $$2}'

## --- Environment -----------------------------------------------------------

venv: ## Create the virtualenv with uv (Python 3.13)
	uv venv --python 3.13

install: ## Install the package with dev extras
	uv pip install -e ".[dev]"

env: ## Create .env from the example (does not overwrite)
	@test -f .env || cp .env.example .env
	@echo "Remember to set KISE_SECRET_KEY in .env"

## --- Run & database --------------------------------------------------------

run: ## Run the API with autoreload
	$(UVICORN) $(APP) --reload

migrate: ## Apply migrations up to head
	$(ALEMBIC) upgrade head

revision: ## Autogenerate a migration: make revision m="message"
	$(ALEMBIC) revision --autogenerate -m "$(m)"

downgrade: ## Roll back one migration
	$(ALEMBIC) downgrade -1

## --- Quality ---------------------------------------------------------------

test: ## Run the test suite
	$(PYTHON) -m pytest -q

lint: ## Lint with ruff
	$(RUFF) check $(SRC)

format: ## Auto-fix lint issues and format with ruff
	$(RUFF) check --fix $(SRC)
	$(RUFF) format $(SRC)

check: lint test ## Lint then test

## --- Frontend assets -------------------------------------------------------

css: ## Build the Tailwind CSS bundle
	npm run css

css-watch: ## Rebuild Tailwind CSS on change
	npm run css:watch

## --- Docker ----------------------------------------------------------------

up: ## Start the full stack (Postgres + backend + pgAdmin)
	docker compose up

up-d: ## Start the full stack in the background (detached)
	docker compose up -d

down: ## Stop the stack
	docker compose down

logs: ## Tail the backend container logs
	docker compose logs -f backend

build: ## Build the Docker images
	docker compose build

## --- Housekeeping ----------------------------------------------------------

clean: ## Remove caches and build artifacts
	rm -rf .pytest_cache .ruff_cache dist build
	find . -type d -name __pycache__ -prune -exec rm -rf {} +
