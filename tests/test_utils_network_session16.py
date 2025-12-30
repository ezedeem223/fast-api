from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy.exc import ProgrammingError

from app.modules.utils import network as net


def test_is_ip_banned_active_and_expired(monkeypatch):
    calls = {"deleted": False, "committed": False}

    class DummyBan:
        def __init__(self, expires_at):
            self.expires_at = expires_at

    class DummySession:
        def __init__(self, result, raise_exc=None):
            self.result = result
            self.raise_exc = raise_exc

        def query(self, *args, **kwargs):
            return self

        def filter(self, *args, **kwargs):
            return self

        def first(self):
            if self.raise_exc:
                raise self.raise_exc
            return self.result

        def delete(self, obj):
            calls["deleted"] = True

        def commit(self):
            calls["committed"] = True

    # Active ban (future)
    future = datetime.now(timezone.utc) + timedelta(hours=1)
    db = DummySession(DummyBan(expires_at=future))
    assert net.is_ip_banned(db, "1.2.3.4") is True
    assert calls["deleted"] is False

    # Expired ban cleans up
    past = datetime.now(timezone.utc) - timedelta(hours=1)
    db = DummySession(DummyBan(expires_at=past))
    assert net.is_ip_banned(db, "1.2.3.4") is False
    assert calls["deleted"] is True
    assert calls["committed"] is True

    # ProgrammingError fails open
    db = DummySession(None, raise_exc=ProgrammingError("x", "y", "z"))
    assert net.is_ip_banned(db, "1.2.3.4") is False


def test_parse_json_response(monkeypatch):
    class DummyResp:
        def json(self):
            return {"ok": True}

    assert net.parse_json_response(DummyResp()) == {"ok": True}

    class BadResp:
        def json(self):
            raise ValueError("no json")

    assert net.parse_json_response(BadResp()) is None


def test_with_retry_success_and_fail(monkeypatch):
    attempts = {"count": 0}

    def flaky():
        attempts["count"] += 1
        if attempts["count"] < 3:
            raise TimeoutError("wait")
        return "ok"

    assert net.with_retry(flaky, retries=3, backoff=0) == "ok"

    def boom():
        raise RuntimeError("other")

    with pytest.raises(RuntimeError):
        net.with_retry(boom, retries=1, backoff=0)


def test_safe_request(monkeypatch):
    def bad():
        raise RuntimeError("fail")

    assert net.safe_request(bad, retries=1, backoff=0) is None

    assert net.safe_request(lambda: "ok") == "ok"
