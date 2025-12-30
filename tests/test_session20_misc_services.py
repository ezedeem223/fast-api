import pytest

from app import models, schemas
from app.modules.utils.security import hash as hash_password
from app.modules.wellness import service as wellness_service
from app.services import reporting
from app.services.business import service as business_service
from app.services.moderation import banned_word_service as moderation_service
from app.services.social.follow_service import FollowService
from fastapi import HTTPException


def _user(session, email="u@example.com", is_admin=False):
    user = models.User(
        email=email,
        hashed_password=hash_password("x"),
        is_verified=True,
        is_admin=is_admin,
    )
    session.add(user)
    session.commit()
    session.refresh(user)
    return user


def test_moderation_crud_and_duplicate(session, monkeypatch):
    admin = _user(session, "admin@example.com", is_admin=True)
    mod_service = moderation_service.BannedWordService(session)
    monkeypatch.setattr(
        moderation_service, "update_ban_statistics", lambda *a, **k: None
    )
    monkeypatch.setattr(moderation_service, "log_admin_action", lambda *a, **k: None)

    ban = mod_service.add_word(
        payload=schemas.BannedWordCreate(word="spam"), current_user=admin
    )
    assert ban.id
    with pytest.raises(HTTPException):
        mod_service.add_word(
            payload=schemas.BannedWordCreate(word="spam"), current_user=admin
        )

    fetched = mod_service.list_words(
        skip=0, limit=10, search="sp", sort_by="word", sort_order="asc"
    )
    assert fetched["total"] >= 1

    mod_service.remove_word(word_id=ban.id, current_user=admin)
    assert session.query(models.BannedWord).filter_by(id=ban.id).first() is None


def test_business_service_and_reporting(session):
    owner = _user(session, "biz@example.com")
    biz_service = business_service.BusinessService(session)
    reg = schemas.BusinessRegistration(
        business_name="B", business_registration_number="123", bank_account_info="bank"
    )
    user_out = biz_service.register_business(current_user=owner, business_info=reg)
    assert user_out.user_type.name.lower() == "business"

    with pytest.raises(HTTPException):
        biz_service.register_business(
            current_user=owner, business_info=reg
        )  # duplicate

    # reporting limits/missing target
    with pytest.raises(HTTPException):
        reporting.submit_report(session, owner, reason="   ", post_id=1)
    with pytest.raises(HTTPException):
        reporting.submit_report(
            session, owner, reason="ok", post_id=None, comment_id=None
        )


def test_follow_service_unfollow_and_missing_user(session):
    svc = FollowService(session)
    u1 = _user(session, "f1@example.com")
    u2 = _user(session, "f2@example.com")
    svc.follow_user(
        background_tasks=None,
        current_user=u1,
        target_user_id=u2.id,
        queue_email_fn=lambda *a, **k: None,
        schedule_email_fn=lambda *a, **k: None,
        notification_manager=type("Dummy", (), {"broadcast": lambda *a, **k: None})(),
        create_notification_fn=lambda *a, **k: None,
    )
    assert (
        session.query(models.Follow)
        .filter_by(follower_id=u1.id, followed_id=u2.id)
        .count()
        == 1
    )
    svc.unfollow_user(
        current_user=u1,
        target_user_id=u2.id,
        background_tasks=None,
        queue_email_fn=lambda *a, **k: None,
    )
    assert (
        session.query(models.Follow)
        .filter_by(follower_id=u1.id, followed_id=u2.id)
        .count()
        == 0
    )
    with pytest.raises(HTTPException):
        svc.follow_user(
            background_tasks=None,
            current_user=u1,
            target_user_id=9999,
            queue_email_fn=lambda *a, **k: None,
            schedule_email_fn=lambda *a, **k: None,
            notification_manager=type(
                "Dummy", (), {"broadcast": lambda *a, **k: None}
            )(),
            create_notification_fn=lambda *a, **k: None,
        )


def test_wellness_service_errors(session):
    svc = wellness_service.WellnessService
    user = _user(session, "well@example.com")
    checkin = svc.update_usage_metrics(db=session, user_id=user.id, usage_minutes=30)
    assert checkin.user_id == user.id

    with pytest.raises(Exception):
        svc.create_wellness_alert(
            db=session, user_id=None, alert_type="alert", severity="high", message="msg"
        )
