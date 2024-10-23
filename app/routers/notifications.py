from fastapi import APIRouter, Depends, HTTPException, Query, BackgroundTasks
from sqlalchemy.orm import Session
from typing import List, Optional
from datetime import datetime, timezone
from ..database import get_db
from .. import schemas, models, oauth2
from ..notifications import NotificationService
from app.firebase_config import send_push_notification

router = APIRouter(prefix="/notifications", tags=["Notifications"])


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
    query = db.query(models.Notification).filter(
        models.Notification.user_id == current_user.id,
        models.Notification.is_deleted == False,
    )

    if not include_read:
        query = query.filter(models.Notification.is_read == False)
    if not include_archived:
        query = query.filter(models.Notification.is_archived == False)
    if category:
        query = query.filter(models.Notification.category == category)
    if priority:
        query = query.filter(models.Notification.priority == priority)

    notifications = (
        query.order_by(models.Notification.created_at.desc())
        .offset(skip)
        .limit(limit)
        .all()
    )

    return notifications


@router.put("/{notification_id}/read")
async def mark_notification_as_read(
    notification_id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(oauth2.get_current_user),
):
    """تحديث حالة قراءة الإشعار"""
    notification_service = NotificationService(db)
    notification = (
        db.query(models.Notification)
        .filter(
            models.Notification.id == notification_id,
            models.Notification.user_id == current_user.id,
        )
        .first()
    )

    if not notification:
        raise HTTPException(status_code=404, detail="Notification not found")

    notification_service.mark_as_read(notification_id, current_user.id)
    return {"message": "Notification marked as read"}


@router.put("/read-all")
async def mark_all_notifications_as_read(
    db: Session = Depends(get_db),
    current_user: models.User = Depends(oauth2.get_current_user),
):
    """تحديث حالة قراءة جميع الإشعارات"""
    db.query(models.Notification).filter(
        models.Notification.user_id == current_user.id,
        models.Notification.is_read == False,
    ).update({"is_read": True, "read_at": datetime.now(timezone.utc)})
    db.commit()
    return {"message": "All notifications marked as read"}


@router.put("/{notification_id}/archive")
async def archive_notification(
    notification_id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(oauth2.get_current_user),
):
    """أرشفة إشعار محدد"""
    notification_service = NotificationService(db)
    notification = (
        db.query(models.Notification)
        .filter(
            models.Notification.id == notification_id,
            models.Notification.user_id == current_user.id,
        )
        .first()
    )

    if not notification:
        raise HTTPException(status_code=404, detail="Notification not found")

    notification_service.archive_notification(notification_id, current_user.id)
    return {"message": "Notification archived"}


@router.delete("/{notification_id}")
async def delete_notification(
    notification_id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(oauth2.get_current_user),
):
    """حذف إشعار محدد"""
    notification = (
        db.query(models.Notification)
        .filter(
            models.Notification.id == notification_id,
            models.Notification.user_id == current_user.id,
        )
        .first()
    )

    if not notification:
        raise HTTPException(status_code=404, detail="Notification not found")

    notification.is_deleted = True
    db.commit()
    return {"message": "Notification deleted"}


@router.get("/preferences", response_model=schemas.NotificationPreferencesOut)
async def get_notification_preferences(
    db: Session = Depends(get_db),
    current_user: models.User = Depends(oauth2.get_current_user),
):
    """الحصول على تفضيلات الإشعارات للمستخدم"""
    preferences = (
        db.query(models.NotificationPreferences)
        .filter(models.NotificationPreferences.user_id == current_user.id)
        .first()
    )

    if not preferences:
        # إنشاء تفضيلات افتراضية إذا لم تكن موجودة
        preferences = models.NotificationPreferences(user_id=current_user.id)
        db.add(preferences)
        db.commit()
        db.refresh(preferences)

    return preferences


@router.put("/preferences", response_model=schemas.NotificationPreferencesOut)
async def update_notification_preferences(
    preferences: schemas.NotificationPreferencesUpdate,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(oauth2.get_current_user),
):
    """تحديث تفضيلات الإشعارات"""
    user_preferences = (
        db.query(models.NotificationPreferences)
        .filter(models.NotificationPreferences.user_id == current_user.id)
        .first()
    )

    if not user_preferences:
        user_preferences = models.NotificationPreferences(user_id=current_user.id)
        db.add(user_preferences)

    for key, value in preferences.dict(exclude_unset=True).items():
        setattr(user_preferences, key, value)

    db.commit()
    db.refresh(user_preferences)
    return user_preferences


@router.get("/unread-count")
async def get_unread_notifications_count(
    db: Session = Depends(get_db),
    current_user: models.User = Depends(oauth2.get_current_user),
):
    """الحصول على عدد الإشعارات غير المقروءة"""
    notification_service = NotificationService(db)
    count = notification_service.get_unread_count(current_user.id)
    return {"unread_count": count}


@router.post("/test-channels")
async def test_notification_channels(
    db: Session = Depends(get_db),
    current_user: models.User = Depends(oauth2.get_current_user),
    background_tasks: BackgroundTasks = None,
):
    """اختبار قنوات الإشعارات المختلفة"""
    notification_service = NotificationService(db, background_tasks)
    test_notification = await notification_service.create_notification(
        user_id=current_user.id,
        content="This is a test notification",
        notification_type="test",
        priority=models.NotificationPriority.LOW,
        category=models.NotificationCategory.SYSTEM,
        metadata={"test": True},
    )
    return {"message": "Test notifications sent successfully"}


@router.get("/statistics", response_model=schemas.NotificationStatistics)
async def get_notification_statistics(
    db: Session = Depends(get_db),
    current_user: models.User = Depends(oauth2.get_current_user),
    days: int = Query(30, ge=1, le=365),
):
    """الحصول على إحصائيات الإشعارات"""
    start_date = datetime.now(timezone.utc) - timedelta(days=days)

    stats = {
        "total_count": db.query(models.Notification)
        .filter(models.Notification.user_id == current_user.id)
        .count(),
        "unread_count": db.query(models.Notification)
        .filter(
            models.Notification.user_id == current_user.id,
            models.Notification.is_read == False,
        )
        .count(),
        "categories_distribution": db.query(
            models.Notification.category,
            func.count(models.Notification.id).label("count"),
        )
        .filter(
            models.Notification.user_id == current_user.id,
            models.Notification.created_at >= start_date,
        )
        .group_by(models.Notification.category)
        .all(),
        "priorities_distribution": db.query(
            models.Notification.priority,
            func.count(models.Notification.id).label("count"),
        )
        .filter(
            models.Notification.user_id == current_user.id,
            models.Notification.created_at >= start_date,
        )
        .group_by(models.Notification.priority)
        .all(),
        "daily_notifications": db.query(
            func.date_trunc("day", models.Notification.created_at).label("date"),
            func.count(models.Notification.id).label("count"),
        )
        .filter(
            models.Notification.user_id == current_user.id,
            models.Notification.created_at >= start_date,
        )
        .group_by(text("date"))
        .order_by(text("date"))
        .all(),
    }

    return stats


@router.post("/retry")
async def retry_failed_notifications(
    notification_ids: List[int],
    db: Session = Depends(get_db),
    current_user: models.User = Depends(oauth2.get_current_user),
):
    """إعادة محاولة إرسال الإشعارات الفاشلة"""
    if not current_user.is_admin:
        raise HTTPException(status_code=403, detail="Not authorized")

    notification_service = NotificationService(db)
    results = []

    for notification_id in notification_ids:
        success = await notification_service.retry_failed_notification(notification_id)
        results.append({"notification_id": notification_id, "success": success})

    return {"results": results}


@router.post("/cleanup")
async def cleanup_old_notifications(
    days: int = Query(default=30, ge=1, le=365),
    db: Session = Depends(get_db),
    current_user: models.User = Depends(oauth2.get_current_user),
):
    """تنظيف الإشعارات القديمة"""
    if not current_user.is_admin:
        raise HTTPException(status_code=403, detail="Not authorized")

    notification_service = NotificationService(db)
    await notification_service.cleanup_old_notifications(days)
    return {"message": f"Successfully archived notifications older than {days} days"}


@router.get("/analytics")
async def get_notification_analytics(
    db: Session = Depends(get_db),
    current_user: models.User = Depends(oauth2.get_current_user),
    days: int = Query(default=30, ge=1, le=365),
):
    """الحصول على إحصائيات الإشعارات"""
    if not current_user.is_admin:
        raise HTTPException(status_code=403, detail="Not authorized")

    start_date = datetime.now(timezone.utc) - timedelta(days=days)

    stats = (
        db.query(
            func.count(models.Notification.id).label("total"),
            func.count(case((models.Notification.status == "DELIVERED", 1))).label(
                "delivered"
            ),
            func.count(case((models.Notification.status == "FAILED", 1))).label(
                "failed"
            ),
            func.avg(models.Notification.retry_count).label("avg_retries"),
            func.count(case((models.Notification.is_read == True, 1))).label("read"),
        )
        .filter(models.Notification.created_at >= start_date)
        .first()
    )

    return {
        "total_notifications": stats.total,
        "delivered_notifications": stats.delivered,
        "failed_notifications": stats.failed,
        "average_retries": float(stats.avg_retries or 0),
        "read_notifications": stats.read,
        "period_days": days,
    }


@router.post("/send-push")
async def send_push(
    notification: schemas.PushNotification,
    current_user: models.User = Depends(oauth2.get_current_user),
):
    response = send_push_notification(
        token=notification.device_token,
        title=notification.title,
        body=notification.content,
        data=notification.extra_data,
    )
    return {"success": bool(response), "message_id": response if response else None}


@router.get("/statistics/delivery", response_model=Dict[str, Any])
async def get_delivery_statistics(
    db: Session = Depends(get_db),
    current_user: models.User = Depends(oauth2.get_current_user),
):
    if not current_user.is_admin:
        raise HTTPException(status_code=403, detail="Admin access required")

    stats = await notification_service.get_delivery_statistics()
    return stats


@router.post("/bulk", response_model=List[schemas.NotificationOut])
async def create_bulk_notifications(
    notifications: List[schemas.NotificationCreate],
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(oauth2.get_current_admin),
):
    return await notification_service.bulk_create_notifications(notifications)
