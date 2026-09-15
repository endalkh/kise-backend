"""Configuration, read from the environment with a ``KISE_`` prefix.

Nothing outside ``platform/`` reads settings: adapters are constructed with plain arguments, so a
test can build one without touching the environment.
"""

from __future__ import annotations

import os
from functools import lru_cache

from pydantic import Field, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

INSECURE_DEFAULT_SECRET = "change-me-to-a-long-random-string"


class Settings(BaseSettings):
    """Everything Kise needs to boot."""

    model_config = SettingsConfigDict(
        env_prefix="KISE_", env_file=".env", env_file_encoding="utf-8", extra="ignore"
    )

    secret_key: str = INSECURE_DEFAULT_SECRET
    # PostgreSQL is the database Kise runs on. The URL uses the psycopg 3 driver
    # (``postgresql+psycopg``); docker-compose brings up a matching instance. SQLite still works by
    # pointing KISE_DATABASE_URL at a ``sqlite://`` URL, which is what the test suite does.
    database_url: str = "postgresql+psycopg://kise:kise@localhost:5432/kise"
    access_token_expire_minutes: int = 60 * 24 * 7  # a week
    default_currency: str = "ETB"
    cors_origins: list[str] = Field(default_factory=lambda: ["*"])
    debug: bool = False
    # Where the landing page's download buttons point. Each renders only when set; with all three
    # empty (no build published yet) the page shows a "coming soon" note instead of a dead link.
    app_store_url: str = ""
    play_store_url: str = ""
    # A direct link — an APK, a TestFlight invite, a GitHub release.
    app_download_url: str = ""

    @field_validator("default_currency")
    @classmethod
    def _currency_is_three_letters(cls, value: str) -> str:
        if len(value) != 3 or not value.isalpha():
            raise ValueError("KISE_DEFAULT_CURRENCY must be three letters, e.g. ETB")
        return value.upper()

    @model_validator(mode="before")
    @classmethod
    def _adopt_platform_database_url(cls, data: dict) -> dict:
        """Fall back to a platform-provided ``DATABASE_URL`` when ``KISE_DATABASE_URL`` is unset.

        Heroku (and similar) attach Postgres by exporting a plain ``DATABASE_URL`` env var, not one
        under our ``KISE_`` prefix. When the operator has not set ``KISE_DATABASE_URL`` explicitly,
        adopt that platform value so a managed database works with no extra configuration. An
        explicit ``KISE_DATABASE_URL`` always wins.
        """
        if isinstance(data, dict) and not data.get("database_url"):
            platform_url = os.environ.get("DATABASE_URL")
            if platform_url:
                data["database_url"] = platform_url
        return data

    @field_validator("database_url")
    @classmethod
    def _normalise_database_scheme(cls, value: str) -> str:
        """Rewrite bare Postgres schemes to the psycopg 3 driver Kise runs on.

        Managed providers hand out URLs like ``postgres://...`` or ``postgresql://...``; SQLAlchemy
        needs the driver spelled out as ``postgresql+psycopg://...``. Rewrite only the two bare
        Postgres forms and leave everything else (an already-qualified URL, or ``sqlite://`` used by
        the tests) untouched.
        """
        for prefix in ("postgres://", "postgresql://"):
            if value.startswith(prefix):
                return "postgresql+psycopg://" + value[len(prefix) :]
        return value

    @property
    def is_secret_key_insecure(self) -> bool:
        """True when the shipped placeholder is still in use.

        The app factory logs a warning for this rather than refusing to start, so local development
        works out of the box while a deployment has no excuse.
        """
        return self.secret_key == INSECURE_DEFAULT_SECRET or len(self.secret_key) < 32


@lru_cache
def get_settings() -> Settings:
    return Settings()
