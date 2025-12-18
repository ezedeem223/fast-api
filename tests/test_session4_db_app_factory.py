import os
import json
import pytest
from sqlalchemy import text
from tests.testclient import TestClient

from app.core.database import query_helpers, session as db_session
from app.core.app_factory import create_app
from app.core.config import settings


def test_paginate_and_cursor_edge_cases(session):
    # seed simple model using User
    from app.modules.users.models import User

    users = [User(email=f"u{i}@ex.com", hashed_password="x") for i in range(3)]
    session.add_all(users)
    session.commit()

    base = session.query(User)
    paged = query_helpers.paginate_query(base, skip=-1, limit=1000).all()
    assert len(paged) == 3

    # cursor pagination invalid cursor ignored; next_cursor present
    result = query_helpers.cursor_paginate(base, cursor="bad", limit=2, cursor_column="id", order_desc=True)
    assert result["count"] == 2
    assert result["has_next"] is True
    assert result["next_cursor"]

    # optimize_count_query drops ordering
    ordered = base.order_by(User.id.desc())
    assert query_helpers.optimize_count_query(ordered) == 3


def test_session_engine_configuration_and_bad_url(monkeypatch):
    # SQLite args include check_same_thread and now function registered
    url = "sqlite:///./tests/test_temp.db"
    engine = db_session.build_engine(url)
    assert engine.url.drivername.startswith("sqlite")
    with engine.connect() as conn:
        # hook adds now() only to global engine; here just ensure connection works
        assert conn.execute(text("select 1")).scalar() == 1

    # Postgres branch: use fake URL to inspect kwargs without connecting
    kwargs = db_session._engine_kwargs("postgresql://user:pass@localhost:5432/db")
    assert kwargs["pool_size"] == 100 and kwargs["max_overflow"] == 200

    # invalid URL should raise in make_url
    with pytest.raises(Exception):
        db_session._engine_kwargs("://bad-url")


def test_app_factory_https_trusted_hosts_and_static_fallback(tmp_path, monkeypatch):
    # enforce HTTPS and allowed hosts
    settings.force_https = True
    monkeypatch.setattr(settings.__class__, "allowed_hosts", ["example.com"], raising=False)
    settings.static_root = str(tmp_path / "static_missing")
    settings.uploads_root = str(tmp_path / "uploads_missing")
    app = create_app()
    with TestClient(app) as client:
        # readiness endpoints still function with missing static/uploads (auto-created)
        resp = client.get("/livez", headers={"host": "example.com"})
        assert resp.status_code == 200

        # paths should exist now
        assert (tmp_path / "static_missing").exists()
        assert (tmp_path / "uploads_missing").exists()

        # ensure middleware mounted: force_https adds httpsredirect middleware header on redirect
        # simulate request to readyz with Redis missing
        r = client.get("/readyz", headers={"host": "example.com"})
        assert r.status_code in (200, 503)

        # TrustedHost middleware rejects bad host
        bad = client.get("/", headers={"host": "evil.com"})
        assert bad.status_code in (400, 403)
