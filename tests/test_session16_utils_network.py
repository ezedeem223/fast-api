from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

from app import models
from app.modules.utils import network


def test_get_client_ip_prefers_forwarded():
    req = SimpleNamespace(
        headers={"X-Forwarded-For": "1.1.1.1, 2.2.2.2"},
        client=SimpleNamespace(host="9.9.9.9"),
    )
    assert network.get_client_ip(req) == "1.1.1.1"

    req2 = SimpleNamespace(headers={}, client=SimpleNamespace(host="8.8.8.8"))
    assert network.get_client_ip(req2) == "8.8.8.8"


def test_is_ip_banned_handles_expiry(session):
    active = models.IPBan(
        ip_address="10.0.0.1",
        reason="x",
        expires_at=datetime.now(timezone.utc) + timedelta(hours=1),
    )
    expired = models.IPBan(
        ip_address="10.0.0.2",
        reason="y",
        expires_at=datetime.now(timezone.utc) - timedelta(hours=1),
    )
    session.add_all([active, expired])
    session.commit()

    assert network.is_ip_banned(session, "10.0.0.1") is True
    # Expired ban should be removed and return False
    assert network.is_ip_banned(session, "10.0.0.2") is False
    assert session.query(models.IPBan).filter_by(ip_address="10.0.0.2").first() is None


def test_detect_ip_evasion_private_vs_public(session):
    user = models.User(email="net16@example.com", hashed_password="x", is_verified=True)
    session.add(user)
    session.commit()
    session.refresh(user)

    session.add_all(
        [
            models.UserSession(user_id=user.id, ip_address="192.168.0.1"),
            models.UserSession(user_id=user.id, ip_address="172.16.0.5"),
        ]
    )
    session.commit()

    assert network.detect_ip_evasion(session, user.id, "8.8.8.8") is True
    assert network.detect_ip_evasion(session, user.id, "192.168.0.9") is False


def test_parse_json_response_and_safe_request(monkeypatch):
    class Resp:
        def json(self):
            return {"ok": True}

    class BadResp:
        def json(self):
            raise ValueError("no json")

    assert network.parse_json_response(Resp()) == {"ok": True}
    assert network.parse_json_response(BadResp()) is None

    calls = {"count": 0}

    def flaky():
        calls["count"] += 1
        if calls["count"] < 2:
            raise TimeoutError("wait")
        return "done"

    monkeypatch.setattr(network.time, "sleep", lambda _: None)
    assert network.with_retry(flaky, retries=3, backoff=0.01) == "done"

    def always_fail():
        raise RuntimeError("boom")

    assert network.safe_request(always_fail, retries=1) is None
