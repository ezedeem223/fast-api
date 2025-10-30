from datetime import timedelta
from types import SimpleNamespace

from app import moderation
from app import models


class DummySession:
    def __init__(self, scalar_result=0):
        self.scalar_result = scalar_result
        self.added = []
        self.commits = 0

    def add(self, obj):
        self.added.append(obj)

    def commit(self):
        self.commits += 1

    def query(self, *args, **kwargs):
        class DummyQuery:
            def __init__(self, result):
                self.result = result

            def filter(self, *args, **kwargs):
                return self

            def scalar(self):
                return self.result

            def first(self):
                return None

        return DummyQuery(self.scalar_result)


def test_warn_user_records_warning(monkeypatch):
    session = DummySession()
    user = SimpleNamespace(
        id=1,
        warning_count=0,
        last_warning_date=None,
        ban_count=0,
        current_ban_end=None,
        total_ban_duration=timedelta(0),
    )

    def fake_get_model_by_id(db, model, identifier):
        if model is models.User:
            return user
        raise AssertionError("Unexpected model lookup")

    monkeypatch.setattr(moderation, "get_model_by_id", fake_get_model_by_id)

    moderation.warn_user(session, 1, "Be careful")

    assert user.warning_count == 1
    assert session.commits == 1
    assert any(isinstance(obj, models.UserWarning) for obj in session.added)


def test_warn_user_triggers_ban_on_threshold(monkeypatch):
    session = DummySession()
    user = SimpleNamespace(
        id=1,
        warning_count=moderation.WARNING_THRESHOLD - 1,
        last_warning_date=None,
        ban_count=0,
        current_ban_end=None,
        total_ban_duration=timedelta(0),
    )

    def fake_get_model_by_id(db, model, identifier):
        if model is models.User:
            return user
        raise AssertionError("Unexpected model lookup")

    monkeypatch.setattr(moderation, "get_model_by_id", fake_get_model_by_id)

    moderation.warn_user(session, 1, "Final warning")

    assert user.ban_count == 1
    assert any(isinstance(obj, models.UserBan) for obj in session.added)


def test_calculate_ban_duration_progression():
    assert moderation.calculate_ban_duration(1) == timedelta(days=1)
    assert moderation.calculate_ban_duration(2) == timedelta(days=7)
    assert moderation.calculate_ban_duration(3) == timedelta(days=30)
    assert moderation.calculate_ban_duration(4) == timedelta(days=365)


def test_process_report_updates_and_checks(monkeypatch):
    session = DummySession()
    report = SimpleNamespace(
        id=5,
        reported_user_id=7,
        is_valid=False,
        reviewed_at=None,
        reviewed_by=None,
    )
    user = SimpleNamespace(id=7, total_reports=0, valid_reports=0)

    def fake_get_model_by_id(db, model, identifier):
        if model is models.Report and identifier == 5:
            return report
        if model is models.User and identifier == 7:
            return user
        raise AssertionError("Unexpected model lookup")

    triggered = {}

    def fake_check_auto_ban(db, user_id):
        triggered["user"] = user_id

    monkeypatch.setattr(moderation, "get_model_by_id", fake_get_model_by_id)
    monkeypatch.setattr(moderation, "check_auto_ban", fake_check_auto_ban)

    moderation.process_report(session, 5, True, reviewer_id=42)

    assert report.is_valid is True
    assert report.reviewed_by == 42
    assert user.total_reports == 1
    assert user.valid_reports == 1
    assert triggered["user"] == 7


def test_check_auto_ban_uses_threshold(monkeypatch):
    session = DummySession(scalar_result=moderation.REPORT_THRESHOLD)
    called = {}

    monkeypatch.setattr(
        moderation,
        "ban_user",
        lambda db, user_id, reason: called.setdefault("user", user_id),
    )

    moderation.check_auto_ban(session, 8)

    assert called["user"] == 8
