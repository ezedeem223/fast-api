from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks, Query
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
from app.firebase_config import send_push_notification  # Firebase push notifications

router = APIRouter(prefix="/notifications", tags=["Notifications"])

# === Notifications Endpoints ===


@router.get("/", response_model=List[schemas.NotificationOut])
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
    """
    الحصول على قائمة الإشعارات للمستخدم الحالي
    Get the list of notifications for the current user.
    """
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


@router.get("/feed", response_model=schemas.NotificationFeedResponse)
async def get_notification_feed(
    db: Session = Depends(get_db),
    current_user: models.User = Depends(oauth2.get_current_user),
    cursor: Optional[int] = Query(None, ge=1),
    limit: int = Query(25, ge=1, le=100),
    include_read: bool = False,
    include_archived: bool = False,
    category: Optional[NotificationCategory] = None,
    priority: Optional[NotificationPriority] = None,
    status: Optional[NotificationStatus] = None,
    mark_seen: bool = True,
    mark_read: bool = False,
):
    """
    Provide a cursor-based feed for the in-app notifications center.
    """
    notification_service = NotificationService(db)
    return await notification_service.get_notification_feed(
        user_id=current_user.id,
        cursor=cursor,
        limit=limit,
        include_read=include_read,
        include_archived=include_archived,
        category=category,
        priority=priority,
        status=status,
        mark_seen=mark_seen,
        mark_read=mark_read,
    )


@router.get("/summary", response_model=schemas.NotificationSummary)
async def get_notification_summary(
    db: Session = Depends(get_db),
    current_user: models.User = Depends(oauth2.get_current_user),
):
    """
    Return badge-friendly counts of unread and unseen notifications.
    """
    notification_service = NotificationService(db)
    return await notification_service.get_unread_summary(current_user.id)


@router.put("/{notification_id}/read")
async def mark_notification_as_read(
    notification_id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(oauth2.get_current_user),
):
    """
    تحديث حالة قراءة الإشعار
    Mark a specific notification as read.
    """
    notification_service = NotificationService(db)
    # Service method handles marking the notification as read
    return await notification_service.mark_as_read(notification_id, current_user.id)


@router.put("/read-all")
async def mark_all_notifications_as_read(
    db: Session = Depends(get_db),
    current_user: models.User = Depends(oauth2.get_current_user),
):
    """
    تحديث حالة قراءة جميع الإشعارات
    Mark all notifications as read.
    """
    notification_service = NotificationService(db)
    return await notification_service.mark_all_as_read(current_user.id)


@router.put("/{notification_id}/archive")
async def archive_notification(
    notification_id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(oauth2.get_current_user),
):
    """
    أرشفة إشعار محدد
    Archive a specific notification.
    """
    notification_service = NotificationService(db)
    return await notification_service.archive_notification(
        notification_id, current_user.id
    )


@router.delete("/{notification_id}")
async def delete_notification(
    notification_id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(oauth2.get_current_user),
):
    """
    حذف إشعار محدد
    Delete a specific notification.
    """
    notification_service = NotificationService(db)
    return await notification_service.delete_notification(
        notification_id, current_user.id
    )


# === Preferences Management ===


@router.get("/preferences", response_model=schemas.NotificationPreferencesOut)
async def get_notification_preferences(
    db: Session = Depends(get_db),
    current_user: models.User = Depends(oauth2.get_current_user),
):
    """
    الحصول على تفضيلات الإشعارات للمستخدم
    Retrieve the user's notification preferences.
    """
    notification_service = NotificationService(db)
    return await notification_service.get_user_preferences(current_user.id)


@router.put("/preferences", response_model=schemas.NotificationPreferencesOut)
async def update_notification_preferences(
    preferences: schemas.NotificationPreferencesUpdate,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(oauth2.get_current_user),
):
    """
    تحديث تفضيلات الإشعارات
    Update the user's notification preferences.
    """
    notification_service = NotificationService(db)
    return await notification_service.update_user_preferences(
        current_user.id, preferences
    )


# === Analytics and Statistics ===


@router.get("/unread-count")
async def get_unread_notifications_count(
    db: Session = Depends(get_db),
    current_user: models.User = Depends(oauth2.get_current_user),
):
    """
    الحصول على عدد الإشعارات غير المقروءة
    Get the count of unread notifications.
    """
    notification_service = NotificationService(db)
    count = await notification_service.get_unread_count(current_user.id)
    return {"unread_count": count}


@router.get("/statistics", response_model=schemas.NotificationStatistics)
async def get_notification_statistics(
    db: Session = Depends(get_db),
    current_user: models.User = Depends(oauth2.get_current_user),
    days: int = Query(30, ge=1, le=365),
):
    """
    الحصول على إحصائيات الإشعارات
    Retrieve notification statistics for a specified period.
    """
    analytics = NotificationAnalyticsService(db)
    return await analytics.get_user_statistics(current_user.id, days)


@router.get("/analytics")
async def get_notification_analytics(
    db: Session = Depends(get_db),
    current_user: models.User = Depends(oauth2.get_current_admin),
    days: int = Query(default=30, ge=1, le=365),
):
    """
    الحصول على تحليلات متقدمة للإشعارات (للمسؤولين فقط)
    Get advanced analytics for notifications (admin only).
    """
    analytics = NotificationAnalyticsService(db)
    return await analytics.get_detailed_analytics(days)


@router.get("/delivery-stats", response_model=dict)
async def get_delivery_statistics(
    db: Session = Depends(get_db),
    current_user: models.User = Depends(oauth2.get_current_admin),
):
    """
    الحصول على إحصائيات تسليم الإشعارات (للمسؤولين فقط)
    Get delivery statistics for notifications (admin only).
    """
    notification_service = NotificationService(db)
    return await notification_service.get_delivery_statistics()


# === Testing and Debugging ===


@router.post("/test-channels")
async def test_notification_channels(
    db: Session = Depends(get_db),
    current_user: models.User = Depends(oauth2.get_current_user),
    background_tasks: BackgroundTasks = None,
):
    """
    اختبار قنوات الإشعارات المختلفة
    Test different notification channels.
    """
    notification_manager = NotificationManager(db, background_tasks)
    return await notification_manager.test_all_channels(current_user.id)


@router.post("/bulk", response_model=List[schemas.NotificationOut])
async def create_bulk_notifications(
    notifications: List[schemas.NotificationCreate],
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(oauth2.get_current_admin),
):
    """
    إنشاء إشعارات متعددة دفعة واحدة (للمسؤولين فقط)
    Create bulk notifications (admin only).
    """
    notification_service = NotificationService(db, background_tasks)
    return await notification_service.bulk_create_notifications(notifications)


@router.put("/cleanup")
async def cleanup_old_notifications(
    days: int = Query(default=30, ge=1, le=365),
    db: Session = Depends(get_db),
    current_user: models.User = Depends(oauth2.get_current_admin),
):
    """
    تنظيف الإشعارات القديمة (للمسؤولين فقط)
    Clean up old notifications (admin only).
    """
    notification_service = NotificationService(db)
    await notification_service.cleanup_old_notifications(days)
    return {"message": f"تم أرشفة الإشعارات الأقدم من {days} يوم"}


# === Additional Endpoints from Second File ===


@router.post("/retry")
async def retry_failed_notifications(
    notification_ids: List[int],
    db: Session = Depends(get_db),
    current_user: models.User = Depends(oauth2.get_current_user),
):
    """
    إعادة محاولة إرسال الإشعارات الفاشلة
    Retry sending failed notifications (admin only).
    """
    if not current_user.is_admin:
        raise HTTPException(status_code=403, detail="Not authorized")
    notification_service = NotificationService(db)
    results = []
    for notification_id in notification_ids:
        # Retry each failed notification using the service method
        success = await notification_service.retry_failed_notification(notification_id)
        results.append({"notification_id": notification_id, "success": success})
    return {"results": results}


@router.post("/send-push")
async def send_push(
    notification: schemas.PushNotification,
    current_user: models.User = Depends(oauth2.get_current_user),
):
    """
    إرسال إشعار دفع عبر Firebase
    Send a push notification using Firebase.
    """
    response = send_push_notification(
        token=notification.device_token,
        title=notification.title,
        body=notification.content,
        data=notification.extra_data,
    )
    return {"success": bool(response), "message_id": response if response else None}


@router.get("/statistics/delivery", response_model=Dict[str, Any])
async def get_delivery_stats(
    db: Session = Depends(get_db),
    current_user: models.User = Depends(oauth2.get_current_user),
):
    """
    الحصول على إحصائيات تسليم الإشعارات بالتفصيل
    Get detailed delivery statistics for notifications (admin only).
    """
    if not current_user.is_admin:
        raise HTTPException(status_code=403, detail="Admin access required")
    notification_service = NotificationService(db)
    stats = await notification_service.get_delivery_statistics()
    return stats


# === Comment Notification Handler Class ===


class CommentNotificationHandler:
    """
    A class to handle comment-related notifications.
    """

    def __init__(self, db: Session, background_tasks: BackgroundTasks):
        # Initialize with the database session and background tasks
        self.db = db
        self.background_tasks = background_tasks
        self.notification_service = NotificationService(db, background_tasks)

    async def handle_new_comment(self, comment: models.Comment, post: models.Post):
        """
        معالجة إشعارات التعليقات الجديدة
        Handle new comment notifications.
        """
        # Notify the post owner if the comment is from a different user
        if comment.owner_id != post.owner_id:
            await self.notification_service.create_notification(
                user_id=post.owner_id,
                content=f"{comment.owner.username} commented on your post",
                notification_type="new_comment",
                priority=NotificationPriority.MEDIUM,
                category=NotificationCategory.SOCIAL,
                link=f"/post/{post.id}#comment-{comment.id}",
            )

        # If the comment is a reply, notify the parent comment owner
        if comment.parent_id:
            parent_comment = (
                self.db.query(models.Comment)
                .filter(models.Comment.id == comment.parent_id)
                .first()
            )
            if parent_comment and parent_comment.owner_id != comment.owner_id:
                await self.notification_service.create_notification(
                    user_id=parent_comment.owner_id,
                    content=f"{comment.owner.username} replied to your comment",
                    notification_type="comment_reply",
                    priority=NotificationPriority.MEDIUM,
                    category=NotificationCategory.SOCIAL,
                    link=f"/post/{post.id}#comment-{comment.id}",
                )
