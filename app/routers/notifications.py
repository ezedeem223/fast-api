from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks, Query, Response
from sqlalchemy.orm import Session
from typing import List, Optional
from datetime import datetime, timezone
from .. import models, schemas, oauth2
from ..database import get_db
from ..notifications import (
    NotificationService,
    NotificationManager,
    NotificationAnalytics,
    MessageNotificationHandler,
    CommentNotificationHandler,
    send_real_time_notification,
)

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
    category: Optional[models.NotificationCategory] = None,
    priority: Optional[models.NotificationPriority] = None,
):
    """الحصول على قائمة الإشعارات للمستخدم الحالي"""
    notification_service = NotificationService(db)
    query = notification_service.build_notifications_query(
        user_id=current_user.id,
        include_read=include_read,
        include_archived=include_archived,
        category=category,
        priority=priority,
    )
    return await notification_service.execute_query(query, skip, limit)


@router.put("/{notification_id}/read")
async def mark_notification_as_read(
    notification_id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(oauth2.get_current_user),
):
    """تحديث حالة قراءة الإشعار"""
    notification_service = NotificationService(db)
    return await notification_service.mark_as_read(notification_id, current_user.id)


@router.put("/read-all")
async def mark_all_notifications_as_read(
    db: Session = Depends(get_db),
    current_user: models.User = Depends(oauth2.get_current_user),
):
    """تحديث حالة قراءة جميع الإشعارات"""
    notification_service = NotificationService(db)
    return await notification_service.mark_all_as_read(current_user.id)


@router.put("/{notification_id}/archive")
async def archive_notification(
    notification_id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(oauth2.get_current_user),
):
    """أرشفة إشعار محدد"""
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
    """حذف إشعار محدد"""
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
    """الحصول على تفضيلات الإشعارات للمستخدم"""
    notification_service = NotificationService(db)
    return await notification_service.get_user_preferences(current_user.id)


@router.put("/preferences", response_model=schemas.NotificationPreferencesOut)
async def update_notification_preferences(
    preferences: schemas.NotificationPreferencesUpdate,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(oauth2.get_current_user),
):
    """تحديث تفضيلات الإشعارات"""
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
    """الحصول على عدد الإشعارات غير المقروءة"""
    notification_service = NotificationService(db)
    count = await notification_service.get_unread_count(current_user.id)
    return {"unread_count": count}


@router.get("/statistics", response_model=schemas.NotificationStatistics)
async def get_notification_statistics(
    db: Session = Depends(get_db),
    current_user: models.User = Depends(oauth2.get_current_user),
    days: int = Query(30, ge=1, le=365),
):
    """الحصول على إحصائيات الإشعارات"""
    analytics = NotificationAnalytics(db)
    return await analytics.get_user_statistics(current_user.id, days)


# === Testing and Debugging ===


@router.post("/test-channels")
async def test_notification_channels(
    db: Session = Depends(get_db),
    current_user: models.User = Depends(oauth2.get_current_user),
    background_tasks: BackgroundTasks = None,
):
    """اختبار قنوات الإشعارات المختلفة"""
    notification_manager = NotificationManager(db, background_tasks)
    return await notification_manager.test_all_channels(current_user.id)


@router.post("/bulk", response_model=List[schemas.NotificationOut])
async def create_bulk_notifications(
    notifications: List[schemas.NotificationCreate],
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(oauth2.get_current_admin),
):
    """إنشاء إشعارات متعددة دفعة واحدة (للمسؤولين فقط)"""
    notification_service = NotificationService(db, background_tasks)
    return await notification_service.bulk_create_notifications(notifications)


@router.put("/cleanup")
async def cleanup_old_notifications(
    days: int = Query(default=30, ge=1, le=365),
    db: Session = Depends(get_db),
    current_user: models.User = Depends(oauth2.get_current_admin),
):
    """تنظيف الإشعارات القديمة (للمسؤولين فقط)"""
    notification_service = NotificationService(db)
    await notification_service.cleanup_old_notifications(days)
    return {"message": f"تم أرشفة الإشعارات الأقدم من {days} يوم"}


@router.get("/analytics")
async def get_notification_analytics(
    db: Session = Depends(get_db),
    current_user: models.User = Depends(oauth2.get_current_admin),
    days: int = Query(default=30, ge=1, le=365),
):
    """الحصول على تحليلات متقدمة للإشعارات (للمسؤولين فقط)"""
    analytics = NotificationAnalytics(db)
    return await analytics.get_detailed_analytics(days)


@router.get("/delivery-stats", response_model=dict)
async def get_delivery_statistics(
    db: Session = Depends(get_db),
    current_user: models.User = Depends(oauth2.get_current_admin),
):
    """الحصول على إحصائيات تسليم الإشعارات (للمسؤولين فقط)"""
    notification_service = NotificationService(db)
    return await notification_service.get_delivery_statistics()
