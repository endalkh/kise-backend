"""The app factory — the top of the composition root.

``create_app`` builds one FastAPI application: it constructs the container (which wires every
adapter, the event bus and the seed-categories subscriber), stores it on ``app.state`` so the
dependencies can reach it, installs the single domain-error handler, adds CORS, and mounts the three
routers that have services behind them.

Deliberately *not* mounted yet: fixed-expenses, monthly summary and the reporting/calendar queries.
Their domain model exists but no application service does, so there is nothing to route to. This is
the documented gap in the README, not an oversight — the factory mounts a router the moment its
service lands, and nothing else here has to change.

Run it with::

    uvicorn kise.platform.api.app:app --reload

``app`` at module scope reads settings from the environment; ``create_app(settings)`` lets a test
inject its own (e.g. an in-memory SQLite URL and a fixed secret).
"""

from __future__ import annotations

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles

from kise.expense_tracking.presentation.routers.categories import router as categories_router
from kise.expense_tracking.presentation.routers.expenses import router as expenses_router
from kise.expense_tracking.presentation.routers.items import router as items_router
from kise.expense_tracking.presentation.routers.reports import router as reports_router
from kise.expense_tracking.presentation.routers.units import router as units_router
from kise.identity.presentation.router import router as auth_router
from kise.platform.api.errors import install_error_handlers
from kise.platform.api.landing import STATIC_DIR, STATIC_PATH, render_landing_page
from kise.platform.config import Settings, get_settings
from kise.platform.container import Container, build_container


def create_app(
    settings: Settings | None = None, *, container: Container | None = None
) -> FastAPI:
    """Build the application. Pass ``settings`` or a ready ``container`` to override defaults."""
    settings = settings or get_settings()
    container = container or build_container(settings)

    from contextlib import asynccontextmanager

    @asynccontextmanager
    async def lifespan(_: FastAPI):
        # Units are global and seedable; ensure the default set exists on boot. Idempotent, so a
        # no-op once seeded. Best-effort: a seeding hiccup must not stop the app from starting.
        try:
            container.seed_units()
        except Exception:  # noqa: BLE001 - seeding is best-effort at startup
            import logging

            logging.getLogger("kise.platform").warning("Unit seeding skipped", exc_info=True)
        yield

    app = FastAPI(
        title="Kise API",
        version="0.1.0",
        summary="Personal expense tracker — Ethiopian and Gregorian calendars, one currency.",
        lifespan=lifespan,
    )
    app.state.container = container

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    install_error_handlers(app)

    app.include_router(auth_router)
    app.include_router(categories_router)
    app.include_router(expenses_router)
    app.include_router(units_router)
    app.include_router(items_router)
    app.include_router(reports_router)

    # The landing page's assets: the favicon and, under static/styles/, the stylesheet compiled by
    # `make web-css`.
    app.mount(STATIC_PATH, StaticFiles(directory=STATIC_DIR), name="static")

    @app.get("/", response_class=HTMLResponse, include_in_schema=False)
    def landing() -> HTMLResponse:
        """The public landing page: what Kise is, and where to download the app."""
        return HTMLResponse(
            render_landing_page(
                download_url=settings.app_download_url,
                app_store_url=settings.app_store_url,
                play_store_url=settings.play_store_url,
            )
        )

    @app.get("/health", tags=["meta"])
    def health() -> dict[str, str]:
        return {"status": "ok"}

    return app


# The ASGI entry point for ``uvicorn kise.platform.api.app:app``.
app = create_app()
