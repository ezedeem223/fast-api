"""Test module for test security settings."""
import importlib


def test_allowed_hosts_and_force_https(monkeypatch):
    """Test case for test allowed hosts and force https."""
    monkeypatch.setenv("ALLOWED_HOSTS", '["example.com","api.example.com"]')
    monkeypatch.setenv("FORCE_HTTPS", "1")
    monkeypatch.setenv("APP_ENV", "production")

    settings_module = importlib.import_module("app.core.config.settings")
    Settings = settings_module.Settings
    new_settings = Settings()

    assert new_settings.allowed_hosts == ["example.com", "api.example.com"]
    assert new_settings.force_https is True
