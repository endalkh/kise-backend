"""Migrations must describe exactly the schema the models declare.

Without this test, the failure mode is quiet and nasty: someone adds a column to a model, the test
suite passes because tests use ``create_all``, and the first deployment hits a table that does not
have the column. Here the migrations are run against an empty database and the result is compared
with the metadata, so a missing migration fails the build instead of production.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from alembic import command
from alembic.autogenerate import compare_metadata
from alembic.config import Config
from alembic.migration import MigrationContext
from alembic.script import ScriptDirectory
from sqlalchemy import create_engine, inspect

from kise.platform.config import get_settings
from kise.platform.database import Base

BACKEND_ROOT = Path(__file__).resolve().parents[2]
EXPECTED_TABLES = {"owners", "categories", "expenses", "fixed_expenses", "settlements"}


@pytest.fixture
def migrated_database(tmp_path, monkeypatch):
    """An empty SQLite file with every migration applied."""
    url = f"sqlite:///{tmp_path / 'migrated.db'}"
    monkeypatch.setenv("KISE_DATABASE_URL", url)
    get_settings.cache_clear()  # env.py reads the settings, which are cached

    config = Config(str(BACKEND_ROOT / "alembic.ini"))
    config.set_main_option("script_location", str(BACKEND_ROOT / "migrations"))
    command.upgrade(config, "head")
    yield url, config
    get_settings.cache_clear()


def test_migrations_create_every_table(migrated_database):
    url, _ = migrated_database
    engine = create_engine(url)
    try:
        tables = set(inspect(engine).get_table_names())
    finally:
        engine.dispose()
    assert EXPECTED_TABLES <= tables, f"missing: {EXPECTED_TABLES - tables}"


def test_migrations_match_the_models(migrated_database):
    """The guard: any drift between a model and the migrations shows up as a diff."""
    url, _ = migrated_database
    engine = create_engine(url)
    try:
        with engine.connect() as connection:
            context = MigrationContext.configure(connection)
            difference = compare_metadata(context, Base.metadata)
    finally:
        engine.dispose()
    assert difference == [], f"models and migrations disagree: {difference}"


def test_downgrade_is_reversible(migrated_database):
    """A migration you cannot undo is a migration you cannot deploy with confidence."""
    url, config = migrated_database
    command.downgrade(config, "base")

    engine = create_engine(url)
    try:
        remaining = set(inspect(engine).get_table_names()) - {"alembic_version"}
    finally:
        engine.dispose()
    assert remaining == set()

    command.upgrade(config, "head")  # and back up again
    engine = create_engine(url)
    try:
        assert EXPECTED_TABLES <= set(inspect(engine).get_table_names())
    finally:
        engine.dispose()


def test_there_is_exactly_one_head():
    """Two heads mean two people generated a migration from the same parent, and the next
    ``upgrade`` will refuse to run."""
    config = Config(str(BACKEND_ROOT / "alembic.ini"))
    config.set_main_option("script_location", str(BACKEND_ROOT / "migrations"))
    scripts = ScriptDirectory.from_config(config)
    heads = scripts.get_heads()
    assert len(heads) == 1, f"expected a single migration head, found {heads}"


def test_every_migration_has_a_downgrade():
    versions = (BACKEND_ROOT / "migrations" / "versions").glob("*.py")
    for path in versions:
        source = path.read_text(encoding="utf-8")
        assert "def downgrade()" in source, f"{path.name} has no downgrade"
        body = source.split("def downgrade()", 1)[1]
        assert body.strip() not in ("-> None:\n    pass", "-> None:"), (
            f"{path.name} has an empty downgrade"
        )
