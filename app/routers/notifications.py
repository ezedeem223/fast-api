"""Notifications router covering preferences, feeds, and delivery/analytics operations."""

from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks, Query, Request
from sqlalchemy.orm import Session
from typing import List, Optional, Dict, Any
from datetime import datetime
from .. import models, schemas, oauth2
from app.modules.notifications.models import (
    NotificationCategory,
    NotificationPriority,
    NotificationStatus,
)
from app.core.database import get_db
from app.modules.notifications.service import (
    NotificationService,
    NotificationManager,
)
from app.modules.notifications.analytics import NotificationAnalyticsService
from app.core.middleware.rate_limit import limiter
from app.core.cache.redis_cache import cache, cache_manager  # Cache helpers.


router = APIRouter(prefix="/notifications", tags=["Notifications"])


# === Notifications Endpoints ===


@router.get("/", response_model=List[schemas.NotificationOut])
@cache(prefix="notifications", ttl=60, include_user=True)  # Cache response for performance.
async def get_notifications(
    db: Session = Depends(get_db),
    current_user: models.User = Depends(oauth2.get_current_user),
    skip: int = Query(0, ge=0),
    limit: int = Query(50, le=100),
    include_read: bool = False,
    include_archived: bool = False,
    category: Optional[NotificationCategory] = None,
    priority: Optional[NotificationPriority] = None,
    status: Optional[NotificationStatus] = None,
    since: Optional[datetime] = None,
):
    """Get the list of notifications for the current user."""
    # Using service layer to build and execute the query
    notification_service = NotificationService(db)
    query = notification_service.build_notifications_query(
        user_id=current_user.id,
        include_read=include_read,
        include_archived=include_archived,
        category=category,
        priority=priority,
        status=status,
        since=since,
    )
    return await notification_service.execute_query(query, skip, limit)


@router.get("/unread-count", response_model=Dict[str, int])
async def get_unread_count(
    db: Session = Depends(get_db),
    current_user: models.User = Depends(oauth2.get_current_user),
):
    """Get the count of unread notifications."""
    notification_service = NotificationService(db)
    return {
        "unread_count": await notification_service.get_unread_count(current_user.id)
    }


@router.get("/summary", response_model=Dict[str, Any])
async def get_notification_summary(
    db: Session = Depends(get_db),
    current_user: models.User = Depends(oauth2.get_current_user),
):
    """Return aggregate counts for unread/unseen notifications."""
    notification_service = NotificationService(db)
    return await notification_service.get_unread_summary(current_user.id)


@router.get("/feed", response_model=Dict[str, Any])
async def get_notification_feed(
    db: Session = Depends(get_db),
    current_user: models.User = Depends(oauth2.get_current_user),
    cursor: Optional[int] = None,
    limit: int = Query(20, ge=1, le=100),
    include_read: bool = False,
    include_archived: bool = False,
    category: Optional[NotificationCategory] = None,
    priority: Optional[NotificationPriority] = None,
    status: Optional[NotificationStatus] = None,
    mark_read: bool = False,
):
    """Cursor-paginated notification feed that marks fetched items as seen."""
    notification_service = NotificationService(db)
    result = await notification_service.get_notification_feed(
        user_id=current_user.id,
        cursor=cursor,
        limit=limit,
        include_read=include_read,
        include_archived=include_archived,
        category=category,
        priority=priority,
        status=status,
        mark_read=mark_read,
    )

    result["notifications"] = [
        schemas.NotificationOut.model_validate(n) for n in result["notifications"]
    ]
    return result


@router.put("/{notification_id}/read")
@limiter.limit("100/minute")
async def mark_notification_as_read(
    request: Request,
    notification_id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(oauth2.get_current_user),
):
    """Mark a specific notification as read."""
    notification_service = NotificationService(db)
    result = await notification_service.mark_as_read(notification_id, current_user.id)

    await cache_manager.invalidate(f"notifications:*u{current_user.id}*")

    return result


@router.put("/mark-all-read")
@limiter.limit("10/minute")
async def mark_all_notifications_as_read(
    request: Request,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(oauth2.get_current_user),
):
    """Mark all notifications as read."""
    notification_service = NotificationService(db)
    result = await notification_service.mark_all_as_read(current_user.id)

    await cache_manager.invalidate(f"notifications:*u{current_user.id}*")

    return result


@router.delete("/{notification_id}")
@limiter.limit("50/minute")
async def delete_notification(
    request: Request,
    notification_id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(oauth2.get_current_user),
):
    """Delete a specific notification."""
    notification_service = NotificationService(db)
    result = await notification_service.delete_notification(
        notification_id, current_user.id
    )

    await cache_manager.invalidate(f"notifications:*u{current_user.id}*")

    return result


@router.put("/{notification_id}/archive")
@limiter.limit("50/minute")
async def archive_notification(
    request: Request,
    notification_id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(oauth2.get_current_user),
):
    """Archive a specific notification."""
    notification_service = NotificationService(db)
    result = await notification_service.archive_notification(
        notification_id, current_user.id
    )

    await cache_manager.invalidate(f"notifications:*u{current_user.id}*")

    return result


@router.delete("/clear-all")
@limiter.limit("5/minute")
async def clear_all_notifications(
    request: Request,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(oauth2.get_current_user),
):
    """Clear all read notifications."""
    notification_service = NotificationService(db)
    result = await notification_service.clear_all_read(current_user.id)

    await cache_manager.invalidate(f"notifications:*u{current_user.id}*")

    return result


# === Notification Preferences ===


@router.get("/preferences", response_model=schemas.NotificationPreferencesOut)
async def get_notification_preferences(
    db: Session = Depends(get_db),
    current_user: models.User = Depends(oauth2.get_current_user),
):
    """Get user's notification preferences."""
    notification_service = NotificationService(db)
    return await notification_service.get_preferences(current_user.id)


@router.put("/preferences", response_model=schemas.NotificationPreferencesOut)
@limiter.limit("20/minute")
async def update_notification_preferences(
    request: Request,
    preferences: schemas.NotificationPreferencesUpdate,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(oauth2.get_current_user),
):
    """Update notification preferences."""
    notification_service = NotificationService(db)
    return await notification_service.update_preferences(current_user.id, preferences)


# === Bulk Operations ===


@router.post("/send-bulk")
@limiter.limit("5/hour")
async def send_bulk_notifications(
    request: Request,
    background_tasks: BackgroundTasks,
    bulk_request: schemas.BulkNotificationRequest,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(oauth2.get_current_user),
):
    """Send bulk notifications (admin only)."""
    # Check if user is admin
    if not current_user.is_admin:
        raise HTTPException(status_code=403, detail="Admin access required")

    notification_manager = NotificationManager(db)
    result = await notification_manager.send_bulk_notifications(
        user_ids=bulk_request.user_ids,
        content=bulk_request.content,
        notification_type=bulk_request.notification_type,
        category=bulk_request.category,
        priority=bulk_request.priority,
        background_tasks=background_tasks,
    )

    return result


@router.put("/bulk-mark-read")
@limiter.limit("20/minute")
async def bulk_mark_as_read(
    request: Request,
    notification_ids: List[int],
    db: Session = Depends(get_db),
    current_user: models.User = Depends(oauth2.get_current_user),
):
    """Mark multiple notifications as read."""
    notification_service = NotificationService(db)
    result = await notification_service.bulk_mark_as_read(
        notification_ids, current_user.id
    )

    await cache_manager.invalidate(f"notifications:*u{current_user.id}*")

    return result


@router.delete("/bulk-delete")
@limiter.limit("20/minute")
async def bulk_delete_notifications(
    request: Request,
    notification_ids: List[int],
    db: Session = Depends(get_db),
    current_user: models.User = Depends(oauth2.get_current_user),
):
    """Delete multiple notifications."""
    notification_service = NotificationService(db)
    result = await notification_service.bulk_delete(notification_ids, current_user.id)

    await cache_manager.invalidate(f"notifications:*u{current_user.id}*")

    return result


# === Scheduled Notifications ===


@router.post("/schedule")
@limiter.limit("10/hour")
async def schedule_notification(
    request: Request,
    background_tasks: BackgroundTasks,
    schedule_request: schemas.ScheduleNotificationRequest,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(oauth2.get_current_user),
):
    """Schedule a notification to be sent later."""
    notification_manager = NotificationManager(db)
    return await notification_manager.schedule_notification(
        user_id=schedule_request.user_id,
        content=schedule_request.content,
        scheduled_for=schedule_request.scheduled_for,
        notification_type=schedule_request.notification_type,
        category=schedule_request.category,
        priority=schedule_request.priority,
        background_tasks=background_tasks,
    )


@router.get("/scheduled", response_model=List[schemas.NotificationOut])
async def get_scheduled_notifications(
    db: Session = Depends(get_db),
    current_user: models.User = Depends(oauth2.get_current_user),
    skip: int = Query(0, ge=0),
    limit: int = Query(50, le=100),
):
    """Get scheduled notifications."""
    notification_service = NotificationService(db)
    return await notification_service.get_scheduled_notifications(
        current_user.id, skip, limit
    )


@router.delete("/scheduled/{notification_id}")
@limiter.limit("50/minute")
async def cancel_scheduled_notification(
    request: Request,
    notification_id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(oauth2.get_current_user),
):
    """Cancel a scheduled notification."""
    notification_service = NotificationService(db)
    return await notification_service.cancel_scheduled_notification(
        notification_id, current_user.id
    )


# === Push Notifications ===


@router.post("/register-device")
@limiter.limit("20/minute")
async def register_device_token(
    request: Request,
    device_data: schemas.DeviceTokenRequest,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(oauth2.get_current_user),
):
    """Register a device token for push notifications."""
    notification_service = NotificationService(db)
    return await notification_service.register_device_token(
        user_id=current_user.id,
        device_token=device_data.device_token,
        device_type=device_data.device_type,
    )


@router.delete("/unregister-device")
@limiter.limit("20/minute")
async def unregister_device_token(
    request: Request,
    device_token: str,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(oauth2.get_current_user),
):
    """Unregister a device token."""
    notification_service = NotificationService(db)
    return await notification_service.unregister_device_token(
        user_id=current_user.id,
        device_token=device_token,
    )


@router.post("/test-push")
@limiter.limit("5/hour")
async def test_push_notification(
    request: Request,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(oauth2.get_current_user),
):
    """Send a test push notification."""
    notification_manager = NotificationManager(db)
    return await notification_manager.send_test_notification(
        user_id=current_user.id,
        background_tasks=background_tasks,
    )


# === Analytics ===


@router.get("/analytics", response_model=schemas.NotificationAnalyticsOut)
async def get_notification_analytics(
    db: Session = Depends(get_db),
    current_user: models.User = Depends(oauth2.get_current_user),
    days: int = Query(30, ge=1, le=365),
):
    """Get notification analytics."""
    analytics_service = NotificationAnalyticsService(db)
    return await analytics_service.get_user_analytics(current_user.id, days)


@router.get("/analytics/delivery-stats", response_model=Dict[str, Any])
async def get_delivery_statistics(
    db: Session = Depends(get_db),
    current_user: models.User = Depends(oauth2.get_current_user),
    days: int = Query(7, ge=1, le=90),
):
    """Get delivery statistics."""
    analytics_service = NotificationAnalyticsService(db)
    return await analytics_service.get_delivery_stats(current_user.id, days)


@router.get("/analytics/engagement", response_model=Dict[str, Any])
async def get_engagement_metrics(
    db: Session = Depends(get_db),
    current_user: models.User = Depends(oauth2.get_current_user),
    days: int = Query(30, ge=1, le=365),
):
    """Get engagement metrics."""
    analytics_service = NotificationAnalyticsService(db)
    return await analytics_service.get_engagement_metrics(current_user.id, days)


# === Groups ===


@router.get("/groups", response_model=List[schemas.NotificationGroupOut])
async def get_notification_groups(
    db: Session = Depends(get_db),
    current_user: models.User = Depends(oauth2.get_current_user),
    skip: int = Query(0, ge=0),
    limit: int = Query(50, le=100),
):
    """Get grouped notifications."""
    notification_service = NotificationService(db)
    return await notification_service.get_notification_groups(
        user_id=current_user.id,
        skip=skip,
        limit=limit,
    )


@router.put("/groups/{group_id}/expand")
async def expand_notification_group(
    group_id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(oauth2.get_current_user),
):
    """Expand a notification group to show all notifications."""
    notification_service = NotificationService(db)
    return await notification_service.expand_group(group_id, current_user.id)


# === Admin Endpoints ===


@router.get("/admin/stats", response_model=Dict[str, Any])
async def get_system_notification_stats(
    db: Session = Depends(get_db),
    current_user: models.User = Depends(oauth2.get_current_user),
    days: int = Query(7, ge=1, le=90),
):
    """Get system-wide notification statistics (admin only)."""
    if not current_user.is_admin:
        raise HTTPException(status_code=403, detail="Admin access required")

    analytics_service = NotificationAnalyticsService(db)
    return await analytics_service.get_system_stats(days)


@router.post("/admin/retry-failed")
@limiter.limit("5/hour")
async def retry_failed_notifications(
    request: Request,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(oauth2.get_current_user),
):
    """Retry failed notifications (admin only)."""
    if not current_user.is_admin:
        raise HTTPException(status_code=403, detail="Admin access required")

    notification_manager = NotificationManager(db)
    return await notification_manager.retry_failed_notifications(background_tasks)


@router.get("/admin/delivery-logs", response_model=List[schemas.DeliveryLogOut])
async def get_delivery_logs(
    db: Session = Depends(get_db),
    current_user: models.User = Depends(oauth2.get_current_user),
    skip: int = Query(0, ge=0),
    limit: int = Query(100, le=500),
    status: Optional[str] = None,
):
    """Get delivery logs (admin only)."""
    if not current_user.is_admin:
        raise HTTPException(status_code=403, detail="Admin access required")

    analytics_service = NotificationAnalyticsService(db)
    return await analytics_service.get_delivery_logs(skip, limit, status)
