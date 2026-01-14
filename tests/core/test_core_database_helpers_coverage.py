"""Additional coverage for core database helpers."""
from __future__ import annotations

import builtins
import types
from pathlib import Path

import pytest

from app import models
from app.core.config import settings
from app.core.database import query_helpers


class _FakeQuery:
    def __init__(self):
        self.calls = []

    def options(self, value):
        self.calls.append(value)
        return self


def test_query_helpers_loads_and_batch(monkeypatch):
    """Cover joined/selectin load helpers and batch relationship handling."""
    fake_query = _FakeQuery()

    class Loader:
        def __init__(self, rel):
            self.rel = rel

        def selectinload(self, rel):
            return f"nested:{self.rel}->{rel}"

    monkeypatch.setattr(query_helpers, "joinedload", lambda rel: f"joined:{rel}")
    monkeypatch.setattr(query_helpers, "selectinload", lambda rel: Loader(rel))

    query_helpers.with_joined_loads(fake_query, "a", "b")
    query_helpers.with_select_loads(fake_query, "c")
    assert fake_query.calls[:2] == ["joined:a", "joined:b"]
    assert isinstance(fake_query.calls[2], Loader)

    fake_query.calls.clear()
    query_helpers.batch_load_relationships(fake_query, ("parent", "child"), "solo")
    assert any("nested:parent->child" == item for item in fake_query.calls)
    assert any(isinstance(item, Loader) and item.rel == "solo" for item in fake_query.calls)


def test_optimize_queries_and_cursor_fallback(session):
    """Exercise optimize_* helpers and cursor fallback branch."""
    query_helpers.optimize_comment_query(session.query(models.Comment))
    query_helpers.optimize_user_query(session.query(models.User))

    users = [
        models.User(email=f"qh_fb_{idx}@example.com", hashed_password="x")
        for idx in range(3)
    ]
    session.add_all(users)
    session.commit()

    last_id = session.query(models.User.id).order_by(models.User.id.desc()).first()[0]
    cursor_payload = query_helpers.json.dumps(last_id)
    cursor = query_helpers.base64.b64encode(cursor_payload.encode("utf-8")).decode(
        "utf-8"
    )
    q = session.query(models.User)
    result = query_helpers.cursor_paginate(q, cursor=cursor, limit=2, order_desc=False)
    assert result["count"] >= 1


def _exec_module(source_path: Path, module_name: str):
    module = types.ModuleType(module_name)
    module.__file__ = str(source_path)
    module.__package__ = "app.core.database"
    exec(compile(source_path.read_text(), module.__file__, "exec"), module.__dict__)
    return module


def test_database_init_uses_settings_database_url(monkeypatch):
    """Cover settings.database_url path in app.core.database.__init__."""
    monkeypatch.setattr(settings, "database_url", "sqlite:///./custom.db", raising=False)
    module = _exec_module(Path("app/core/database/__init__.py"), "app.core.database._test_db_url")
    assert module.SQLALCHEMY_DATABASE_URL == "sqlite:///./custom.db"


def test_database_init_fallback_sqlite(monkeypatch):
    """Cover fallback to sqlite when no env pieces are present."""
    monkeypatch.setattr(settings, "database_url", "", raising=False)
    monkeypatch.setattr(settings, "database_username", None, raising=False)
    monkeypatch.setattr(settings, "database_password", None, raising=False)
    monkeypatch.setattr(settings, "database_hostname", None, raising=False)
    monkeypatch.setattr(settings, "database_name", None, raising=False)

    module = _exec_module(Path("app/core/database/__init__.py"), "app.core.database._test_db_fallback")
    assert module.SQLALCHEMY_DATABASE_URL == "sqlite:///./test.db"


def test_database_init_import_error_branch(monkeypatch):
    """Trigger ImportError path for query_helpers import."""
    source = Path("app/core/database/__init__.py")

    original_import = builtins.__import__

    def fake_import(name, globals=None, locals=None, fromlist=(), level=0):
        if name.endswith("query_helpers"):
            raise ImportError("boom")
        return original_import(name, globals, locals, fromlist, level)

    monkeypatch.setattr(builtins, "__import__", fake_import)
    module = _exec_module(source, "app.core.database._test_db_import_error")
    assert module.__all__ == ["Base", "SessionLocal", "engine", "get_db", "build_engine"]


def test_session_sqlite_registers_now(monkeypatch):
    """Ensure sqlite session module registers now() helper."""
    source = Path("app/core/database/session.py")
    monkeypatch.setattr(settings, "environment", "test", raising=False)
    monkeypatch.setattr(
        settings.__class__,
        "get_database_url",
        lambda _self, use_test=True: "sqlite:///:memory:",
        raising=False,
    )

    module = types.ModuleType("app.core.database._session_sqlite_test")
    module.__file__ = str(source)
    module.__package__ = "app.core.database"
    exec(compile(source.read_text(), module.__file__, "exec"), module.__dict__)

    class FakeConn:
        def __init__(self):
            self.calls = []

        def create_function(self, name, args, fn):
            self.calls.append((name, args, fn))

    fake_conn = FakeConn()
    module._add_sqlite_functions(fake_conn, None)
    assert fake_conn.calls[0][0] == "now"
