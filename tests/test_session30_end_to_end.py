import logging

from app.core.logging_config import setup_logging, JSONFormatter
from app.core.database import get_db
from app.main import app
from app import notifications


def test_health_endpoints_and_ready_failure(client):
    res = client.get("/livez")
    assert res.status_code == 200 and res.json()["status"] == "ok"

    res = client.get("/readyz")
    assert res.status_code == 200

    def failing_db():
        class Dummy:
            def execute(self, *_):
                raise RuntimeError("db down")

            def close(self):
                return None

        yield Dummy()

    app.dependency_overrides[get_db] = failing_db
    try:
        res = client.get("/readyz")
        assert res.status_code == 503
    finally:
        app.dependency_overrides.pop(get_db, None)


def test_metrics_and_logging_json(client, tmp_path):
    first = client.get("/metrics")
    second = client.get("/metrics")
    assert first.status_code == 200
    assert second.status_code == 200
    assert first.text.startswith("# HELP")

    setup_logging(use_json=True, log_dir=str(tmp_path))
    json_handlers = [
        handler
        for handler in logging.getLogger().handlers
        if getattr(handler, "formatter", None)
        and isinstance(handler.formatter, JSONFormatter)
    ]
    assert json_handlers, "Expected JSON formatter when USE_JSON_LOGS=true"


def test_end_to_end_flow_search_like_follow_and_messaging(
    authorized_client, test_user, test_user2, monkeypatch
):
    sent = {}

    async def fake_send(payload, target):
        sent["payload"] = payload
        sent["target"] = target

    monkeypatch.setattr(notifications.manager, "send_personal_message", fake_send)

    post_resp = authorized_client.post(
        "/posts/",
        json={"title": "session30 post", "content": "body content"},
    )
    assert post_resp.status_code == 201
    post_id = post_resp.json()["id"]

    comment_resp = authorized_client.post(
        "/comments/",
        json={"post_id": post_id, "content": "nice post"},
    )
    assert comment_resp.status_code == 201

    msg_resp = authorized_client.post(
        "/message/",
        json={"receiver_id": test_user2["id"], "content": "hello there"},
    )
    assert msg_resp.status_code == 201

    search_resp = authorized_client.post(
        "/search/",
        json={"query": "session30", "sort_by": "relevance"},
    )
    assert search_resp.status_code == 200

    vote_resp = authorized_client.post(
        "/vote/",
        json={"post_id": post_id, "reaction_type": "like"},
    )
    assert vote_resp.status_code == 201

    follow_resp = authorized_client.post(f"/follow/{test_user2['id']}")
    assert follow_resp.status_code == 201

    assert "target" in sent and sent["target"].endswith(str(test_user2["id"]))
