from __future__ import annotations

from app import utils


def test_call_quality_buffers_and_recommendations(monkeypatch):
    utils.quality_buffers.clear()
    score = utils.check_call_quality({"packet_loss": 20, "latency": 150, "jitter": 25}, "call-1")
    assert score < 100
    assert utils.should_adjust_video_quality("call-1") is True
    assert utils.get_recommended_video_quality("call-1") == "low"

    utils.check_call_quality({"packet_loss": 1, "latency": 20, "jitter": 2}, "call-1")
    assert utils.get_recommended_video_quality("call-1") == "medium"

    utils.check_call_quality({"packet_loss": 0, "latency": 5, "jitter": 1}, "call-1")
    assert utils.get_recommended_video_quality("call-1") == "high"


def test_clean_old_quality_buffers(monkeypatch):
    utils.quality_buffers.clear()
    buffer = utils.CallQualityBuffer()
    utils.quality_buffers["stale"] = buffer
    buffer.last_update_time = 0

    monkeypatch.setattr(utils.time, "time", lambda: 1000)
    utils.clean_old_quality_buffers()
    assert "stale" not in utils.quality_buffers
