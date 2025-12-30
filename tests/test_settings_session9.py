import json

import pytest

from app.core.config import settings


def test_allowed_hosts_parsing_json_and_csv(monkeypatch):
    # JSON string list
    monkeypatch.setenv("ALLOWED_HOSTS", '["alpha.com", "beta.com"]')
    refreshed = type(settings)()
    assert refreshed.allowed_hosts == ["alpha.com", "beta.com", "testserver"]

    # CSV list
    monkeypatch.setenv("ALLOWED_HOSTS", "gamma.com,delta.com")
    refreshed = type(settings)()
    assert refreshed.allowed_hosts[:2] == ["gamma.com", "delta.com"]
    assert "testserver" in refreshed.allowed_hosts


def test_force_https_default_in_production(monkeypatch):
    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.delenv("FORCE_HTTPS", raising=False)
    refreshed = type(settings)()
    assert refreshed.force_https is True

    monkeypatch.setenv("FORCE_HTTPS", "0")
    refreshed = type(settings)()
    assert refreshed.force_https is False

    monkeypatch.setenv("FORCE_HTTPS", "true")
    refreshed = type(settings)()
    assert refreshed.force_https is True


def test_read_key_file_relative_and_missing(monkeypatch, tmp_path):
    priv = tmp_path / "priv.pem"
    pub = tmp_path / "pub.pem"
    priv.write_text("PRIVATE KEY")
    pub.write_text("PUBLIC KEY")

    monkeypatch.setenv("RSA_PRIVATE_KEY_PATH", str(priv))
    monkeypatch.setenv("RSA_PUBLIC_KEY_PATH", str(pub))
    refreshed = type(settings)()
    assert refreshed.rsa_private_key == "PRIVATE KEY"
    assert refreshed.rsa_public_key == "PUBLIC KEY"

    missing_path = tmp_path / "missing.pem"
    monkeypatch.setenv("RSA_PRIVATE_KEY_PATH", str(missing_path))
    monkeypatch.setenv("RSA_PUBLIC_KEY_PATH", str(missing_path))
    with pytest.raises(ValueError):
        type(settings)()
