"""Alembic environment.

Two things worth knowing:

* The database URL comes from ``KISE_DATABASE_URL`` (via ``Settings``), not from ``alembic.ini``, so
  migrations and the running app can never disagree about which database they mean.
* Every context's models module is imported before ``target_metadata`` is read. Tables live with
  their bounded context, so autogenerate would silently miss a whole context otherwise — and a
  missing import here would produce a migration that drops tables.
"""

from __future__ import annotations

from logging.config import fileConfig

from alembic import context
from sqlalchemy import engine_from_config, pool

# Importing for the side effect of registering tables on Base.metadata.
import kise.expense_tracking.infrastructure.persistence.models  # noqa: F401,E402
import kise.identity.infrastructure.persistence.models  # noqa: F401,E402
from kise.platform.config import get_settings
from kise.platform.database import Base

config = context.config
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata

database_url = get_settings().database_url
config.set_main_option("sqlalchemy.url", database_url)


def run_migrations_offline() -> None:
    """Emit SQL to stdout instead of running it, for review or for a DBA."""
    context.configure(
        url=database_url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        compare_type=True,
        # SQLite cannot ALTER most things, so Alembic rewrites the table instead.
        render_as_batch=database_url.startswith("sqlite"),
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            compare_type=True,
            render_as_batch=database_url.startswith("sqlite"),
        )
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
