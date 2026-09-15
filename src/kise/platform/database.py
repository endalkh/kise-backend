"""Database plumbing owned by the composition root.

The metadata lives here rather than inside a bounded context because the contexts share one
database. Each context still declares its own tables, in its own
``infrastructure/persistence/entities.py``.
"""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager

from sqlalchemy import Engine, MetaData, create_engine, event
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker
from sqlalchemy.pool import StaticPool

# Explicit constraint names, so migrations can refer to them on any backend.
NAMING_CONVENTION = {
    "ix": "ix_%(table_name)s_%(column_0_N_name)s",
    "uq": "uq_%(table_name)s_%(column_0_N_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}


class Base(DeclarativeBase):
    """Declarative base for the persistence entities.

    Note what this is *not*: aggregates never inherit from it. Persistence entities are a separate
    set of classes, and mappers translate between the two.
    """

    metadata = MetaData(naming_convention=NAMING_CONVENTION)


def build_engine(database_url: str, *, echo: bool = False) -> Engine:
    """Create an engine, with the SQLite-specific settings Kise needs for local development."""
    is_sqlite = database_url.startswith("sqlite")
    # An in-memory database lives inside its connection: give every connection its own and the
    # schema created on one is invisible to the next. StaticPool keeps a single shared connection,
    # which is what makes an in-memory database usable across threads — the TestClient runs the app
    # in a worker thread, so the API's requests would otherwise never see the created schema.
    is_memory = is_sqlite and (":memory:" in database_url or database_url in ("sqlite://",))
    connect_args = {"check_same_thread": False} if is_sqlite else {}
    engine_kwargs: dict[str, object] = {"echo": echo, "future": True, "connect_args": connect_args}
    if is_memory:
        engine_kwargs["poolclass"] = StaticPool
    engine = create_engine(database_url, **engine_kwargs)
    if is_sqlite:
        # SQLite ignores foreign keys unless asked, which would silently defeat the
        # settlement -> fixed_expense constraint.
        @event.listens_for(engine, "connect")
        def _enable_foreign_keys(dbapi_connection, _record):  # pragma: no cover - driver hook
            cursor = dbapi_connection.cursor()
            cursor.execute("PRAGMA foreign_keys=ON")
            cursor.close()

    return engine


def build_session_factory(engine: Engine) -> sessionmaker[Session]:
    return sessionmaker(bind=engine, autoflush=False, expire_on_commit=False, future=True)


def create_all(engine: Engine) -> None:
    """Create the schema. Fine for v1 and tests; Alembic takes over when migrations matter.

    Every context's models module has to be imported before ``create_all``, or its tables are not
    on the metadata. This function is the one place that knows the full list — which is also the
    one place that would need a line added if a fourth context ever owned tables.
    """
    import kise.expense_tracking.infrastructure.persistence.models  # noqa: F401
    import kise.identity.infrastructure.persistence.models  # noqa: F401

    Base.metadata.create_all(engine)


@contextmanager
def session_scope(session_factory: sessionmaker[Session]) -> Iterator[Session]:
    """A transactional scope, used by the Unit of Work and by tests."""
    session = session_factory()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()
