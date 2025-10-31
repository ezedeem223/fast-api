from app.config import Settings, settings


def test_settings_provide_defaults(tmp_path, monkeypatch):
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.delenv("DATABASE_HOSTNAME", raising=False)
    monkeypatch.delenv("DATABASE_USERNAME", raising=False)
    monkeypatch.delenv("DATABASE_NAME", raising=False)

    refreshed = Settings()
    assert refreshed.sqlalchemy_database_uri.startswith("sqlite:///")
    assert refreshed.secret_key
    assert refreshed.mail_from


def test_rsa_keys_are_loaded():
    assert settings.rsa_private_key.startswith("-----BEGIN")
    assert settings.rsa_public_key.startswith("-----BEGIN")
