"""Additional coverage for Settings RSA/DB helper branches."""
from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

from app.core.config.settings import BASE_DIR, Settings


ORIGINAL_LOAD_KEYS = Settings._load_or_generate_rsa_keys


def _make_settings(monkeypatch, **kwargs):
    """Create Settings with RSA loading stubbed to avoid filesystem work."""
    monkeypatch.setattr(Settings, "_load_or_generate_rsa_keys", lambda self: ("priv", "pub"))
    return Settings(**kwargs)


def test_settings_init_hs_fallback_redis_error_and_cors_env(monkeypatch):
    """Cover HS fallback, redis error, CORS env parsing, and jwt key id fallback."""
    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.setenv("CORS_ORIGINS", '["https://a.com", "https://b.com"]')
    monkeypatch.setenv("REDIS_URL", "redis://bad")
    monkeypatch.delenv("JWT_PRIVATE_KEYS", raising=False)
    monkeypatch.delenv("JWT_PUBLIC_KEYS", raising=False)

    monkeypatch.setattr(
        "redis.Redis.from_url",
        lambda *_: (_ for _ in ()).throw(RuntimeError("redis")),
    )

    cfg = _make_settings(
        monkeypatch,
        algorithm="HS256",
        secret_key="secret",
        jwt_private_keys=json.dumps({"kid1": "priv"}),
        jwt_public_keys=json.dumps({"kid1": "pub"}),
        jwt_key_id="missing",
    )

    assert cfg.jwt_key_id == "kid1"
    assert any("https://a.com" in origin for origin in cfg.cors_origins)
    assert "localhost" in cfg.allowed_hosts


def test_settings_init_uses_cors_origins_attribute(monkeypatch):
    """Cover cors_origins attribute branch when env is unset."""
    monkeypatch.delenv("CORS_ORIGINS", raising=False)
    cfg = _make_settings(monkeypatch, cors_origins=["https://custom.example"])
    assert cfg.cors_origins == ["https://custom.example"]


def test_get_database_url_self_value(monkeypatch):
    """Return explicit database_url when env is unset."""
    monkeypatch.delenv("DATABASE_URL", raising=False)
    cfg = _make_settings(monkeypatch, database_url="postgresql://example")
    assert cfg.get_database_url() == "postgresql://example"


def test_get_database_url_components_no_ssl(monkeypatch):
    """Compose DB URL from components without sslmode."""
    for key in [
        "DATABASE_URL",
        "TEST_DATABASE_URL",
        "DATABASE_HOSTNAME",
        "DATABASE_USERNAME",
        "DATABASE_PASSWORD",
        "DATABASE_NAME",
        "DATABASE_PORT",
    ]:
        monkeypatch.delenv(key, raising=False)
    cfg = _make_settings(
        monkeypatch,
        database_hostname="host",
        database_username="user",
        database_password="pass",
        database_name="db",
        database_ssl_mode="",
    )
    expected = f"postgresql+psycopg2://user:pass@host:{cfg.database_port}/db"
    assert cfg.get_database_url() == expected


def test_resolve_test_database_url_components(monkeypatch):
    """Resolve test DB URL from component parts."""
    for key in [
        "DATABASE_URL",
        "TEST_DATABASE_URL",
        "DATABASE_HOSTNAME",
        "DATABASE_USERNAME",
        "DATABASE_PASSWORD",
        "DATABASE_NAME",
        "DATABASE_PORT",
    ]:
        monkeypatch.delenv(key, raising=False)
    cfg = _make_settings(
        monkeypatch,
        database_hostname="host",
        database_username="user",
        database_password="pass",
        database_name="db",
        database_ssl_mode="",
    )
    assert cfg._resolve_test_database_url().endswith("db_test")


def test_resolve_test_database_url_from_candidate(monkeypatch):
    """Derive *_test DB URL from DATABASE_URL env."""
    for key in [
        "TEST_DATABASE_URL",
        "DATABASE_HOSTNAME",
        "DATABASE_USERNAME",
        "DATABASE_PASSWORD",
        "DATABASE_NAME",
        "DATABASE_PORT",
    ]:
        monkeypatch.delenv(key, raising=False)
    monkeypatch.setenv("DATABASE_URL", "postgresql://u:p@h/db")
    cfg = _make_settings(
        monkeypatch,
        database_hostname=None,
        database_username=None,
        database_password=None,
        database_name=None,
    )
    assert cfg._resolve_test_database_url().endswith("db_test")


def test_resolve_test_database_url_sqlite_candidate(monkeypatch):
    """Return sqlite candidate when URL parsing fails."""
    for key in [
        "DATABASE_URL",
        "TEST_DATABASE_URL",
        "DATABASE_HOSTNAME",
        "DATABASE_USERNAME",
        "DATABASE_PASSWORD",
        "DATABASE_NAME",
        "DATABASE_PORT",
    ]:
        monkeypatch.delenv(key, raising=False)
    cfg = _make_settings(
        monkeypatch,
        database_url="sqlite:///./test.db",
        database_hostname=None,
        database_username=None,
        database_password=None,
        database_name=None,
    )

    def boom(*_):
        raise RuntimeError("bad")

    monkeypatch.setattr("sqlalchemy.engine.make_url", boom)
    assert cfg._resolve_test_database_url() == "sqlite:///./test.db"


def test_allow_generated_rsa_keys(monkeypatch):
    """Cover allow-generated RSA key branches."""
    cfg = _make_settings(monkeypatch)
    monkeypatch.setenv("ALLOW_GENERATED_RSA_KEYS", "1")
    assert cfg._allow_generated_rsa_keys() is True

    monkeypatch.delenv("ALLOW_GENERATED_RSA_KEYS", raising=False)
    cfg.environment = "test"
    assert cfg._allow_generated_rsa_keys() is True


def test_rsa_paths_explicit(monkeypatch):
    """Cover rsa path explicit detection."""
    cfg = _make_settings(monkeypatch, rsa_private_key_path="keys/private.pem")
    assert cfg._rsa_paths_explicit() is True

    monkeypatch.setenv("RSA_PRIVATE_KEY_PATH", "keys/private.pem")
    assert cfg._rsa_paths_explicit() is True


def test_keyfile_helpers(tmp_path):
    """Cover keyfile write/generate/derive/normalize helpers."""
    private_pem, public_pem = Settings._generate_rsa_keypair()
    derived = Settings._derive_public_key(private_pem)
    assert "BEGIN PUBLIC KEY" in derived

    normalized = Settings._normalize_pem_env("line1\\nline2")
    assert "\n" in normalized

    path = tmp_path / "key.pem"
    Settings._write_key_file(path, "KEYDATA", "private")
    assert path.read_text() == "KEYDATA"


def test_read_key_file_errors(tmp_path):
    """Cover missing/empty/error branches in _read_key_file."""
    cfg = Settings.__new__(Settings)

    with pytest.raises(ValueError):
        cfg._read_key_file("", "private")

    empty = tmp_path / "empty.pem"
    empty.write_text("", encoding="utf-8")
    with pytest.raises(ValueError):
        cfg._read_key_file(str(empty), "private")

    bad = tmp_path / "bad.pem"
    bad.write_text("data", encoding="utf-8")

    def boom(*_):
        raise IOError("boom")

    monkeypatch = pytest.MonkeyPatch()
    monkeypatch.setattr(Path, "open", boom)
    with pytest.raises(ValueError):
        cfg._read_key_file(str(bad), "private")
    monkeypatch.undo()


def test_parse_key_map_errors(monkeypatch):
    """Cover invalid key map inputs."""
    cfg = _make_settings(monkeypatch)

    with pytest.raises(ValueError):
        cfg._parse_key_map("not-json", "fallback", "LABEL")

    with pytest.raises(ValueError):
        cfg._parse_key_map("[]", "fallback", "LABEL")

    with pytest.raises(ValueError):
        cfg._parse_key_map("{}", "fallback", "LABEL")

    with pytest.raises(ValueError):
        cfg._parse_key_map('{"": "key"}', "fallback", "LABEL")

    with pytest.raises(ValueError):
        cfg._parse_key_map('{"kid": ""}', "fallback", "LABEL")


def test_load_or_generate_rsa_keys_branches(monkeypatch, tmp_path):
    """Cover env/private/generate branches in RSA key loader."""
    cfg = _make_settings(monkeypatch)

    monkeypatch.setenv("RSA_PRIVATE_KEY", "priv\nkey")
    monkeypatch.delenv("RSA_PUBLIC_KEY", raising=False)

    def fake_write(path, key, key_type):
        return (path, key, key_type)

    monkeypatch.setattr(Settings, "_write_key_file", staticmethod(fake_write))
    monkeypatch.setattr(Settings, "_derive_public_key", staticmethod(lambda *_: "pub"))
    private, public = ORIGINAL_LOAD_KEYS(cfg)
    assert "priv" in private

    monkeypatch.delenv("RSA_PRIVATE_KEY", raising=False)
    monkeypatch.setenv("RSA_PUBLIC_KEY", "pub")
    with pytest.raises(ValueError):
        ORIGINAL_LOAD_KEYS(cfg)

    monkeypatch.delenv("RSA_PUBLIC_KEY", raising=False)
    monkeypatch.setattr(Settings, "_rsa_paths_explicit", lambda *_: True)
    monkeypatch.setattr(Settings, "_key_file_present", lambda *_: False)
    monkeypatch.setattr(Settings, "_read_key_file", lambda *_: "key")
    monkeypatch.setattr(Settings, "_allow_generated_rsa_keys", lambda *_: False)
    assert ORIGINAL_LOAD_KEYS(cfg) == ("key", "key")

    monkeypatch.setattr(Settings, "_allow_generated_rsa_keys", lambda *_: True)
    monkeypatch.setattr(Settings, "_key_file_present", lambda *_: False)
    monkeypatch.setattr(Settings, "_generate_rsa_keypair", staticmethod(lambda: ("priv", "pub")))
    private, public = ORIGINAL_LOAD_KEYS(cfg)
    assert private == "priv" and public == "pub"


def test_get_jwt_public_key_fallback(monkeypatch):
    """Return fallback key when kid is missing."""
    cfg = _make_settings(monkeypatch)
    cfg._jwt_public_keys_map = {"default": "pub"}
    cfg._jwt_private_keys_map = {"default": "priv"}
    assert cfg.get_jwt_public_key("missing") == "pub"
