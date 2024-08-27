from celery import Celery
from fastapi_mail import FastMail, MessageSchema, ConnectionConfig
from pydantic import EmailStr
from typing import List
from app.config import settings

# إعداد Celery
celery_app = Celery("worker", broker="pyamqp://guest@localhost//", backend="rpc://")

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


@celery_app.task
def send_email_task(email_to: List[EmailStr], subject: str, body: str):
    """
    مهمة لإرسال البريد الإلكتروني باستخدام Celery.
    """
    message = MessageSchema(
        subject=subject,
        recipients=email_to,  # قائمة المستلمين
        body=body,
        subtype="html",
    )
    fm = FastMail(conf)
    fm.send_message(message)


# مثال على مهمة أخرى
@celery_app.task
def some_other_task(data):
    """
    مثال على مهمة أخرى يمكن معالجتها بواسطة Celery.
    """
    # قم بتنفيذ المهام هنا
    pass
