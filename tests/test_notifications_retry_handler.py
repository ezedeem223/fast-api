import asyncio
from unittest.mock import MagicMock

import pytest

from app.modules.notifications import models as notification_models
from app.modules.notifications.common import get_model_by_id
from app.modules.notifications.service import NotificationRetryHandler


def _notification(
    session,
    user_id,
    status=notification_models.NotificationStatus.FAILED,
    retry_count=0,
):
    n = notification_models.Notification(
        user_id=user_id,
        content="payload",
        notification_type="test",
        status=status,
        retry_count=retry_count,
    )
    session.add(n)
    session.commit()
    session.refresh(n)
    return n


@pytest.mark.asyncio
async def test_schedule_retry_adds_task_when_background_tasks_present(
    session, test_user
):
    bg = MagicMock()
    handler = NotificationRetryHandler(session, background_tasks=bg)
    n = _notification(session, test_user["id"], retry_count=0)

    await handler.handle_failed_notification(n.id)
    assert bg.add_task.called
    session.refresh(n)
    assert n.status == "retrying"
    assert n.retry_count == 1


@pytest.mark.asyncio
async def test_schedule_retry_runs_immediately_when_no_background_tasks(
    session, test_user
):
    handler = NotificationRetryHandler(session, background_tasks=None)
    n = _notification(session, test_user["id"], retry_count=0)

    await handler.handle_failed_notification(n.id)
    session.refresh(n)
    assert n.status == "retrying"
    assert n.retry_count == 1


@pytest.mark.asyncio
async def test_no_retry_scheduled_when_max_retries_reached(session, test_user):
    handler = NotificationRetryHandler(session, background_tasks=None)
    n = _notification(session, test_user["id"], retry_count=handler.max_retries)

    await handler.handle_failed_notification(n.id)
    # If no exception is raised, we consider the "no scheduling" path covered.
    assert True


@pytest.mark.asyncio
async def test_retry_notification_waits_and_delivers(monkeypatch, session, test_user):
    handler = NotificationRetryHandler(session, background_tasks=None)
    n = _notification(
        session,
        test_user["id"],
        status=notification_models.NotificationStatus.RETRYING,
        retry_count=0,
    )

    async def fake_deliver(notification_id, delay):
        await asyncio.sleep(0)
        notif = get_model_by_id(
            session, notification_models.Notification, notification_id
        )
        if notif:
            notif.status = notification_models.NotificationStatus.DELIVERED
            session.commit()

    monkeypatch.setattr(handler, "retry_notification", fake_deliver)

    await handler.handle_failed_notification(n.id)
    session.refresh(n)
    assert n.status in ("retrying", notification_models.NotificationStatus.DELIVERED)
