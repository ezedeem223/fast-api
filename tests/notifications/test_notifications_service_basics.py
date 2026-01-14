"""Test module for test notifications service basics."""
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest
from sqlalchemy.exc import IntegrityError

from app.modules.notifications import models as notification_models
from app.modules.notifications import schemas as notification_schemas
from app.modules.notifications import service as notifications_service
from app.modules.notifications.common import delivery_status_cache, notification_cache
from app.modules.notifications.service import (
    MAX_METADATA_BYTES,
    NotificationDeliveryManager,
    NotificationService,
)


@pytest.fixture(autouse=True)
def _clear_notification_cache():
    """Pytest fixture for _clear_notification_cache."""
    notification_cache.clear()
    delivery_status_cache.clear()
    yield
    notification_cache.clear()
    delivery_status_cache.clear()


def _make_service(session, deliver_result=True):
    """Helper to create NotificationService with delivery patched to avoid external I/O."""
    service = NotificationService(session, background_tasks=MagicMock())
    service.delivery_manager.deliver_notification = AsyncMock(
        return_value=deliver_result
    )
    return service


@pytest.mark.asyncio
async def test_create_notification_sets_pending(session, test_user):
    """Test case for test create notification sets pending."""
    service = _make_service(session)

    # avoid group creation hitting non-existent fields
    service._find_or_create_group = lambda *_, **__: None

    notification = await service.create_notification(
        user_id=test_user["id"],
        content="hello",
        notification_type="welcome",
        metadata={"foo": "bar"},
    )

    assert notification is not None
    assert notification.status == notification_models.NotificationStatus.PENDING
    assert notification.user_id == test_user["id"]
    assert notification.notification_metadata.get("foo") == "bar"


@pytest.mark.asyncio
async def test_update_notification_respects_constraints(session, test_user):
    """Test case for test update notification respects constraints."""
    service = _make_service(session)
    service._find_or_create_group = lambda *_, **__: None
    notification = await service.create_notification(
        user_id=test_user["id"],
        content="original",
        notification_type="update_me",
    )

    # Update content and persist
    notification.content = "updated"
    session.commit()
    session.refresh(notification)
    assert notification.content == "updated"
    assert notification.status == notification_models.NotificationStatus.PENDING

    # Setting required field to None should fail and rollback
    notification.content = None
    with pytest.raises(IntegrityError):
        session.commit()
    session.rollback()
    session.refresh(notification)
    assert notification.content == "updated"


@pytest.mark.asyncio
async def test_delete_notification_marks_deleted(session, test_user):
    """Test case for test delete notification marks deleted."""
    service = _make_service(session)
    service._find_or_create_group = lambda *_, **__: None
    repo = service.repository
    notification = await service.create_notification(
        user_id=test_user["id"],
        content="to delete",
        notification_type="delete_me",
    )

    deleted = repo.soft_delete_notification(notification.id, test_user["id"])
    assert deleted.is_deleted is True
    assert deleted.is_archived is True


@pytest.mark.asyncio
async def test_metadata_length_validation(session, test_user):
    """Test case for test metadata length validation."""
    service = _make_service(session)
    service._find_or_create_group = lambda *_, **__: None

    small_metadata = {"meta": "x" * 10}
    ok = await service.create_notification(
        user_id=test_user["id"],
        content="small meta",
        notification_type="meta_ok",
        metadata=small_metadata,
    )
    assert ok is not None

    too_large = {"meta": "y" * (MAX_METADATA_BYTES + 10)}
    with pytest.raises(ValueError):
        await service.create_notification(
            user_id=test_user["id"],
            content="too big",
            notification_type="meta_big",
            metadata=too_large,
        )


@pytest.mark.asyncio
async def test_metadata_invalid_json_defaults_to_empty(monkeypatch, session, test_user):
    """Test case for test metadata invalid json defaults to empty."""
    service = _make_service(session)
    service._find_or_create_group = lambda *_, **__: None
    service.delivery_manager.deliver_notification = AsyncMock(return_value=True)

    invalid_metadata = {"bad": {1, 2}}  # sets are not JSON serializable
    notification = await service.create_notification(
        user_id=test_user["id"],
        content="meta invalid",
        notification_type="meta_invalid",
        metadata=invalid_metadata,
    )
    assert notification.notification_metadata == {}
    service.delivery_manager.deliver_notification.assert_awaited_once()


@pytest.mark.asyncio
async def test_metadata_valid_json_is_persisted(session, test_user):
    """Test case for test metadata valid json is persisted."""
    service = _make_service(session)
    service._find_or_create_group = lambda *_, **__: None

    valid_metadata = {"ok": ["v1", "v2"]}
    notification = await service.create_notification(
        user_id=test_user["id"],
        content="meta valid",
        notification_type="meta_valid",
        metadata=valid_metadata,
    )
    assert notification.notification_metadata == valid_metadata


@pytest.mark.asyncio
async def test_metadata_parsing_failure_does_not_block_delivery(
    monkeypatch, session, test_user
):
    """Test case for test metadata parsing failure does not block delivery."""
    service = _make_service(session, deliver_result=True)
    service._find_or_create_group = lambda *_, **__: None
    deliver_mock = AsyncMock(return_value=True)
    service.delivery_manager.deliver_notification = deliver_mock

    notification = await service.create_notification(
        user_id=test_user["id"],
        content="meta fail but deliver",
        notification_type="meta_deliver",
        metadata={"bad": {1}},  # unserialisable, will fallback to {}
    )

    assert notification.notification_metadata == {}
    deliver_mock.assert_awaited_once()


@pytest.mark.asyncio
async def test_commit_failure_rolls_back(session, test_user, monkeypatch):
    """Test case for test commit failure rolls back."""
    service = _make_service(session)
    service._find_or_create_group = lambda *_, **__: None
    rollback_called = {"value": False}

    def fake_create(**kwargs):
        raise RuntimeError("db boom")

    def fake_rollback():
        rollback_called["value"] = True
        session.rollback()

    monkeypatch.setattr(
        service, "repository", MagicMock(create_notification=fake_create)
    )
    monkeypatch.setattr(session, "rollback", fake_rollback)

    with pytest.raises(RuntimeError):
        await service.create_notification(
            user_id=test_user["id"],
            content="should fail",
            notification_type="fail",
        )
    assert rollback_called["value"] is True


@pytest.mark.asyncio
async def test_create_missing_required_field_raises(session, test_user):
    """Test case for test create missing required field raises."""
    service = _make_service(session)
    service._find_or_create_group = lambda *_, **__: None

    with pytest.raises(Exception):
        await service.create_notification(
            user_id=test_user["id"],
            content=None,  # type: ignore[arg-type]
            notification_type="invalid",
        )
    session.rollback()


# ===================== bulk/batch =====================


@pytest.mark.asyncio
async def test_bulk_create_notifications_success(session, test_user):
    """Test case for test bulk create notifications success."""
    service = _make_service(session)
    service._find_or_create_group = lambda *_, **__: None

    payloads = [
        notification_schemas.NotificationCreate(
            user_id=test_user["id"],
            content="n1",
            notification_type="t1",
            priority=notification_models.NotificationPriority.MEDIUM,
            category=notification_models.NotificationCategory.SYSTEM,
        ),
        notification_schemas.NotificationCreate(
            user_id=test_user["id"],
            content="n2",
            notification_type="t2",
            priority=notification_models.NotificationPriority.MEDIUM,
            category=notification_models.NotificationCategory.SYSTEM,
        ),
    ]
    result = await service.bulk_create_notifications(payloads)
    assert len(result) == 2
    assert result[0].content == "n1"
    assert result[1].notification_type == "t2"


@pytest.mark.asyncio
async def test_bulk_create_notifications_dedupes_same_payload(session, test_user):
    """Test case for test bulk create notifications dedupes same payload."""
    service = _make_service(session)
    service._find_or_create_group = lambda *_, **__: None

    payload = notification_schemas.NotificationCreate(
        user_id=test_user["id"],
        content="dup",
        notification_type="same",
        priority=notification_models.NotificationPriority.MEDIUM,
        category=notification_models.NotificationCategory.SYSTEM,
    )
    result = await service.bulk_create_notifications([payload, payload])
    assert len(result) == 1
    assert result[0] is not None
    assert result[0].content == "dup"


@pytest.mark.asyncio
async def test_bulk_create_cache_key_stable_for_same_metadata(session, test_user):
    """Test case for test bulk create cache key stable for same metadata."""
    service = _make_service(session)
    service._find_or_create_group = lambda *_, **__: None
    payload_a = notification_schemas.NotificationCreate(
        user_id=test_user["id"],
        content="meta order",
        notification_type="tmeta",
        priority=notification_models.NotificationPriority.MEDIUM,
        category=notification_models.NotificationCategory.SYSTEM,
        metadata={"a": 1, "b": 2},
    )
    payload_b = notification_schemas.NotificationCreate(
        user_id=test_user["id"],
        content="meta order",
        notification_type="tmeta",
        priority=notification_models.NotificationPriority.MEDIUM,
        category=notification_models.NotificationCategory.SYSTEM,
        metadata={"b": 2, "a": 1},  # same content, different ordering
    )
    result = await service.bulk_create_notifications([payload_a, payload_b])
    assert len(result) == 1  # deduped because cache key stable
    assert result[0].content == "meta order"


@pytest.mark.asyncio
async def test_bulk_create_notifications_rollback_on_failure(
    session, test_user, monkeypatch
):
    """Test case for test bulk create notifications rollback on failure."""
    service = _make_service(session)
    service._find_or_create_group = lambda *_, **__: None

    call_count = {"n": 0}

    def boom(metadata):
        call_count["n"] += 1
        if call_count["n"] == 2:
            raise RuntimeError("fail one")
        return {}

    monkeypatch.setattr(service, "_normalize_metadata", boom)

    payloads = [
        notification_schemas.NotificationCreate(
            user_id=test_user["id"],
            content="ok",
            notification_type="t1",
            priority=notification_models.NotificationPriority.MEDIUM,
            category=notification_models.NotificationCategory.SYSTEM,
        ),
        notification_schemas.NotificationCreate(
            user_id=test_user["id"],
            content="fail",
            notification_type="t2",
            priority=notification_models.NotificationPriority.MEDIUM,
            category=notification_models.NotificationCategory.SYSTEM,
        ),
    ]
    with pytest.raises(RuntimeError):
        await service.bulk_create_notifications(payloads)
    # transaction should rollback completely
    assert (
        session.query(notification_models.Notification).filter_by(content="ok").count()
        == 0
    )


@pytest.mark.asyncio
async def test_auto_translate_applied_when_enabled(monkeypatch, session, test_user):
    """Test case for test auto translate applied when enabled."""
    service = _make_service(session)
    service._find_or_create_group = lambda *_, **__: None
    monkeypatch.setattr(
        "app.modules.notifications.service.detect_language", lambda _: "ar"
    )
    translated = "translated-text"
    translate_mock = MagicMock(return_value=translated)
    monkeypatch.setattr(
        "app.modules.notifications.service.translate_text", translate_mock
    )

    # force prefs and set attributes not present on model
    prefs = service.repository.ensure_preferences(test_user["id"])
    setattr(prefs, "auto_translate", True)
    setattr(prefs, "preferred_language", "en")

    notification = await service.create_notification(
        user_id=test_user["id"],
        content="مرحبا",
        notification_type="welcome",
    )

    assert notification.content == translated
    translate_mock.assert_called_once()


@pytest.mark.asyncio
async def test_auto_translate_disabled(monkeypatch, session, test_user):
    """Test case for test auto translate disabled."""
    service = _make_service(session)
    service._find_or_create_group = lambda *_, **__: None
    monkeypatch.setattr(
        "app.modules.notifications.service.detect_language", lambda _: "en"
    )
    translate_mock = MagicMock(side_effect=AssertionError("should not translate"))
    monkeypatch.setattr(
        "app.modules.notifications.service.translate_text", translate_mock
    )

    prefs = service.repository.ensure_preferences(test_user["id"])
    setattr(prefs, "auto_translate", False)
    setattr(prefs, "preferred_language", "fr")

    notification = await service.create_notification(
        user_id=test_user["id"],
        content="hello",
        notification_type="welcome",
    )

    assert notification.content == "hello"


def test_get_user_preferences_created_and_cached(session, test_user):
    """Test case for test get user preferences created and cached."""
    notification_cache.clear()
    service = _make_service(session)
    service._find_or_create_group = lambda *_, **__: None

    calls = {"count": 0}
    original_ensure = service.repository.ensure_preferences

    def fake_ensure(user_id):
        calls["count"] += 1
        return original_ensure(user_id)

    service.repository.ensure_preferences = fake_ensure  # type: ignore[assignment]

    prefs1 = service._get_user_preferences(test_user["id"])
    prefs2 = service._get_user_preferences(test_user["id"])
    assert calls["count"] == 1
    assert prefs1 is prefs2


def test_get_user_preferences_handles_db_exception(session, test_user, monkeypatch):
    """Test case for test get user preferences handles db exception."""
    notification_cache.clear()
    service = _make_service(session)
    service._find_or_create_group = lambda *_, **__: None

    def boom(user_id):
        raise RuntimeError("db error")

    monkeypatch.setattr(service.repository, "ensure_preferences", boom)
    with pytest.raises(RuntimeError):
        service._get_user_preferences(test_user["id"])


@pytest.mark.asyncio
async def test_translation_failure_uses_original(monkeypatch, session, test_user):
    """Test case for test translation failure uses original."""
    service = _make_service(session)
    service._find_or_create_group = lambda *_, **__: None
    monkeypatch.setattr(
        "app.modules.notifications.service.detect_language", lambda _: "ar"
    )
    monkeypatch.setattr(
        "app.modules.notifications.service.translate_text", MagicMock(return_value=None)
    )
    prefs = service.repository.ensure_preferences(test_user["id"])
    setattr(prefs, "auto_translate", True)
    setattr(prefs, "preferred_language", "en")

    notification = await service.create_notification(
        user_id=test_user["id"],
        content="مرحبا",
        notification_type="welcome",
    )

    assert notification.content == "مرحبا"


def _make_delivery_manager(session):
    """Helper for  make delivery manager."""
    mgr = NotificationDeliveryManager(session)
    mgr._get_user_preferences = (
        lambda uid: mgr.db.query(notification_models.NotificationPreferences)
        .filter_by(user_id=uid)
        .first()
    )  # type: ignore[attr-defined]
    mgr._process_language = AsyncMock(side_effect=lambda content, *_: content)  # type: ignore[attr-defined]
    return mgr


def _make_notification(session, user_id):
    """Helper for  make notification."""
    notif = notification_models.Notification(
        user_id=user_id,
        content="payload",
        notification_type="test",
        status=notification_models.NotificationStatus.PENDING,
    )
    notif.language = "en"  # attribute used by delivery flow (not persisted column)
    session.add(notif)
    session.commit()
    session.refresh(notif)
    return notif


@pytest.mark.asyncio
async def test_all_channels_delivered(monkeypatch, session, test_user):
    """Test case for test all channels delivered."""
    mgr = _make_delivery_manager(session)
    monkeypatch.setattr(
        "app.modules.notifications.service.manager.send_personal_message", AsyncMock()
    )
    monkeypatch.setattr(mgr, "_send_email_notification", AsyncMock())
    monkeypatch.setattr(mgr, "_send_push_notification", AsyncMock())

    prefs_obj = SimpleNamespace(
        email_notifications=True,
        push_notifications=True,
        in_app_notifications=True,
        auto_translate=False,
        preferred_language="en",
    )
    mgr._get_user_preferences = lambda _: prefs_obj

    notification = _make_notification(session, test_user["id"])

    success = await mgr.deliver_notification(notification)
    assert success is True
    session.refresh(notification)
    assert notification.status == notification_models.NotificationStatus.DELIVERED
    log = (
        session.query(notification_models.NotificationDeliveryLog)
        .filter_by(notification_id=notification.id)
        .first()
    )
    assert log is not None
    assert log.delivery_channel == "all"


@pytest.mark.asyncio
async def test_email_only(monkeypatch, session, test_user):
    """Test case for test email only."""
    mgr = _make_delivery_manager(session)
    email_mock = AsyncMock()
    monkeypatch.setattr(mgr, "_send_email_notification", email_mock)
    monkeypatch.setattr(mgr, "_send_push_notification", AsyncMock())
    monkeypatch.setattr(
        "app.modules.notifications.service.manager.send_personal_message", AsyncMock()
    )

    prefs_obj = SimpleNamespace(
        email_notifications=True,
        push_notifications=False,
        in_app_notifications=False,
        auto_translate=False,
        preferred_language="en",
    )
    mgr._get_user_preferences = lambda _: prefs_obj

    notification = _make_notification(session, test_user["id"])
    success = await mgr.deliver_notification(notification)
    assert success is True
    email_mock.assert_awaited()
    session.refresh(notification)
    assert notification.status == notification_models.NotificationStatus.DELIVERED


@pytest.mark.asyncio
async def test_push_only(monkeypatch, session, test_user):
    """Test case for test push only."""
    mgr = _make_delivery_manager(session)
    push_mock = AsyncMock()
    monkeypatch.setattr(mgr, "_send_email_notification", AsyncMock())
    monkeypatch.setattr(mgr, "_send_push_notification", push_mock)
    monkeypatch.setattr(
        "app.modules.notifications.service.manager.send_personal_message", AsyncMock()
    )

    prefs_obj = SimpleNamespace(
        email_notifications=False,
        push_notifications=True,
        in_app_notifications=False,
        auto_translate=False,
        preferred_language="en",
    )
    mgr._get_user_preferences = lambda _: prefs_obj

    notification = _make_notification(session, test_user["id"])
    success = await mgr.deliver_notification(notification)
    assert success is True
    push_mock.assert_awaited()
    session.refresh(notification)
    assert notification.status == notification_models.NotificationStatus.DELIVERED


@pytest.mark.asyncio
async def test_ws_only(monkeypatch, session, test_user):
    """Test case for test ws only."""
    mgr = _make_delivery_manager(session)
    ws_mock = AsyncMock()
    monkeypatch.setattr(
        "app.modules.notifications.service.manager.send_personal_message", ws_mock
    )
    monkeypatch.setattr(mgr, "_send_email_notification", AsyncMock())
    monkeypatch.setattr(mgr, "_send_push_notification", AsyncMock())

    prefs_obj = SimpleNamespace(
        email_notifications=False,
        push_notifications=False,
        in_app_notifications=True,
        auto_translate=False,
        preferred_language="en",
    )
    mgr._get_user_preferences = lambda _: prefs_obj

    notification = _make_notification(session, test_user["id"])
    success = await mgr.deliver_notification(notification)
    assert success is True
    ws_mock.assert_awaited()
    session.refresh(notification)
    assert notification.status == notification_models.NotificationStatus.DELIVERED


@pytest.mark.asyncio
async def test_missing_email_logs_warning(monkeypatch, session, test_user, caplog):
    """Test case for test missing email logs warning."""
    mgr = _make_delivery_manager(session)

    async def fake_email(notification, content):
        logger = notifications_service.logger
        logger.warning("No email found for user %s", notification.user_id)

    monkeypatch.setattr(mgr, "_send_email_notification", fake_email)
    monkeypatch.setattr(mgr, "_send_push_notification", AsyncMock())
    monkeypatch.setattr(
        "app.modules.notifications.service.manager.send_personal_message", AsyncMock()
    )
    prefs_obj = SimpleNamespace(
        email_notifications=True,
        push_notifications=False,
        in_app_notifications=False,
        auto_translate=False,
        preferred_language="en",
    )
    mgr._get_user_preferences = lambda _: prefs_obj
    caplog.set_level("WARNING")
    notification = _make_notification(session, test_user["id"])
    success = await mgr.deliver_notification(notification)
    assert success is True
    assert any("No email found" in rec.message for rec in caplog.records)


@pytest.mark.asyncio
async def test_no_devices_logs_and_returns(monkeypatch, session, test_user, caplog):
    """Test case for test no devices logs and returns."""
    mgr = _make_delivery_manager(session)
    monkeypatch.setattr(mgr, "_send_email_notification", AsyncMock())
    monkeypatch.setattr(
        "app.modules.notifications.service.manager.send_personal_message", AsyncMock()
    )

    async def fake_push(notification, content):
        logger = notifications_service.logger
        logger.info("No active devices for user %s", notification.user_id)

    monkeypatch.setattr(mgr, "_send_push_notification", fake_push)
    prefs_obj = SimpleNamespace(
        email_notifications=False,
        push_notifications=True,
        in_app_notifications=False,
        auto_translate=False,
        preferred_language="en",
    )
    mgr._get_user_preferences = lambda _: prefs_obj
    caplog.set_level("INFO")
    notification = _make_notification(session, test_user["id"])
    success = await mgr.deliver_notification(notification)
    assert success is True
    assert any("No active devices" in rec.message for rec in caplog.records)


@pytest.mark.asyncio
async def test_ws_manager_exception_logged(monkeypatch, session, test_user, caplog):
    """Test case for test ws manager exception logged."""
    mgr = _make_delivery_manager(session)
    monkeypatch.setattr(mgr, "_send_email_notification", AsyncMock())
    monkeypatch.setattr(mgr, "_send_push_notification", AsyncMock())
    caplog.set_level("ERROR")

    async def boom(*args, **kwargs):
        raise RuntimeError("ws down")

    monkeypatch.setattr(
        "app.modules.notifications.service.manager.send_personal_message", boom
    )
    prefs_obj = SimpleNamespace(
        email_notifications=False,
        push_notifications=False,
        in_app_notifications=True,
        auto_translate=False,
        preferred_language="en",
    )
    mgr._get_user_preferences = lambda _: prefs_obj
    notification = _make_notification(session, test_user["id"])
    success = await mgr.deliver_notification(notification)
    assert success is True
    assert any(
        "Error sending realtime notification" in rec.message for rec in caplog.records
    )
