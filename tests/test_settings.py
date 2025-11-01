"""Unit tests for configuration defaults and boolean parsing."""

import pytest

from app.config import Settings


@pytest.fixture()
def clean_env(monkeypatch):
    """Ensure database-related environment variables do not leak between tests."""

    env_vars = [
        "DATABASE_URL",
        "DATABASE_HOSTNAME",
        "DATABASE_PORT",
        "DATABASE_PASSWORD",
        "DATABASE_NAME",
        "DATABASE_USERNAME",
    ]
    for var in env_vars:
        monkeypatch.delenv(var, raising=False)
    yield


def test_settings_database_url_defaults_to_sqlite(clean_env, monkeypatch):
    """When no explicit database information is provided, Settings should fall back to SQLite."""

    monkeypatch.setenv("DATABASE_URL", "")

    settings = Settings(database_url_override=None)
    assert settings.database_url.endswith("app.db")


def test_boolean_environment_parsing(monkeypatch):
    """The helper should treat common truthy strings as True."""

    monkeypatch.setenv("REQUIRE_VERIFIED_FOR_COMMUNITY_CREATION", "TrUe")
    settings = Settings()
    assert settings.require_verified_for_community_creation is True

    monkeypatch.setenv("REQUIRE_VERIFIED_FOR_COMMUNITY_CREATION", "off")
    settings = Settings()
    assert settings.require_verified_for_community_creation is False


def test_max_owned_communities_default(monkeypatch):
    """The maximum allowed communities should have a sensible default."""

    monkeypatch.delenv("MAX_OWNED_COMMUNITIES", raising=False)
    settings = Settings()
    assert settings.MAX_OWNED_COMMUNITIES == 3

    monkeypatch.setenv("MAX_OWNED_COMMUNITIES", "10")
    settings = Settings()
    assert settings.MAX_OWNED_COMMUNITIES == 10
