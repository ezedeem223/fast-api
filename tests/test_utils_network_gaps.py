from app.modules.utils import network


def test_safe_request_retries_timeouts(monkeypatch, caplog):
    attempts = {"count": 0}

    def flaky():
        attempts["count"] += 1
        if attempts["count"] < 3:
            raise TimeoutError("late")
        return "ok"

    monkeypatch.setattr(network.time, "sleep", lambda *_: None)
    caplog.set_level("WARNING")
    result = network.safe_request(flaky, retries=3, backoff=0)
    assert result == "ok"
    assert attempts["count"] == 3
    assert any("network_timeout" in rec.message for rec in caplog.records)


def test_parse_json_response_handles_non_json(caplog):
    class BadResp:
        def json(self):
            raise ValueError("not json")

    caplog.set_level("WARNING")
    parsed = network.parse_json_response(BadResp())
    assert parsed is None
    assert any("non_json_response" in rec.message for rec in caplog.records)


def test_safe_request_logs_network_error(caplog):
    def bad():
        raise RuntimeError("boom")

    caplog.set_level("ERROR")
    result = network.safe_request(bad, retries=1)
    assert result is None
    assert any("network_request_failed" in rec.message for rec in caplog.records)
