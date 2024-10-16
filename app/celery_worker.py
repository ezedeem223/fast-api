from celery import Celery
from fastapi_mail import FastMail, MessageSchema, ConnectionConfig
from pydantic import EmailStr
from typing import List
from app.config import settings
from app.database import SessionLocal
from app import models
from datetime import datetime

# إعداد Celery
celery_app = Celery(
    "worker",
    broker=settings.celery_broker_url,
    backend=settings.celery_backend_url,
)

# إعدادات البريد الإلكتروني
conf = ConnectionConfig(
    MAIL_USERNAME=settings.mail_username,
    MAIL_PASSWORD=settings.mail_password,
    MAIL_FROM=settings.mail_from,
    MAIL_PORT=settings.mail_port,
    MAIL_SERVER=settings.mail_server,
    MAIL_FROM_NAME="YourAppName Notifications",
    MAIL_TLS=True,
    MAIL_SSL=False,
    USE_CREDENTIALS=True,
)

# إنشاء كائن FastMail مرة واحدة لاستخدامه في جميع المهام
fm = FastMail(conf)


@celery_app.task
def send_email_task(email_to: List[EmailStr], subject: str, body: str):
    """
    مهمة لإرسال البريد الإلكتروني باستخدام Celery.
    """
    try:
        message = MessageSchema(
            subject=subject,
            recipients=email_to,
            body=body,
            subtype="html",
        )
        fm.send_message(message)
    except Exception as e:
        print(f"Failed to send email: {e}")


@celery_app.task
def unblock_user(blocker_id: int, blocked_id: int):
    db = SessionLocal()
    try:
        block = (
            db.query(models.Block)
            .filter(
                models.Block.blocker_id == blocker_id,
                models.Block.blocked_id == blocked_id,
            )
            .first()
        )
        if block:
            db.delete(block)
            db.commit()

            # إرسال إشعار بالبريد الإلكتروني عن إلغاء الحظر
            blocker = db.query(models.User).filter(models.User.id == blocker_id).first()
            blocked = db.query(models.User).filter(models.User.id == blocked_id).first()
            if blocker and blocked:
                send_email_task.delay(
                    [blocked.email],
                    "تم إلغاء الحظر",
                    f"لقد تم إلغاء الحظر عنك من قبل المستخدم {blocker.username}.",
                )
    finally:
        db.close()


@celery_app.task
def clean_expired_blocks():
    db = SessionLocal()
    try:
        expired_blocks = (
            db.query(models.Block).filter(models.Block.ends_at < datetime.now()).all()
        )
        for block in expired_blocks:
            db.delete(block)

            # إرسال إشعار بالبريد الإلكتروني عن انتهاء الحظر
            blocker = (
                db.query(models.User).filter(models.User.id == block.blocker_id).first()
            )
            blocked = (
                db.query(models.User).filter(models.User.id == block.blocked_id).first()
            )
            if blocker and blocked:
                send_email_task.delay(
                    [blocked.email],
                    "انتهاء مدة الحظر",
                    f"لقد انتهت مدة الحظر المفروض عليك من قبل المستخدم {blocker.username}.",
                )

        db.commit()
    finally:
        db.close()


# إعداد جدول المهام الدورية
celery_app.conf.beat_schedule = {
    "clean-expired-blocks": {
        "task": "app.celery_worker.clean_expired_blocks",
        "schedule": 3600.0,  # كل ساعة
    },
}


# مثال على مهمة أخرى
@celery_app.task
def some_other_task(data):
    """
    مثال على مهمة أخرى يمكن معالجتها بواسطة Celery.
    """
    # قم بتنفيذ المهام هنا
    pass
