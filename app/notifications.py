from fastapi import BackgroundTasks, WebSocket
from fastapi_mail import FastMail, MessageSchema, ConnectionConfig
from pydantic import EmailStr
from typing import List
from .config import settings

# إعدادات البريد الإلكتروني
conf = ConnectionConfig(
    MAIL_USERNAME=settings.mail_username,
    MAIL_PASSWORD=settings.mail_password,
    MAIL_FROM=settings.mail_from,
    MAIL_PORT=settings.mail_port,
    MAIL_SERVER=settings.mail_server,
    MAIL_FROM_NAME="YourAppName Notifications",
    MAIL_STARTTLS=True,
    MAIL_SSL_TLS=False,
    USE_CREDENTIALS=True,
)


def send_email_notification(
    background_tasks: BackgroundTasks, email_to: List[EmailStr], subject: str, body: str
):
    message = MessageSchema(
        subject=subject,
        recipients=email_to,
        body=body,
        subtype="html",
    )
    fm = FastMail(conf)
    background_tasks.add_task(fm.send_message, message)


# إدارة اتصالات WebSocket
class ConnectionManager:
    def __init__(self):
        self.active_connections: List[WebSocket] = []

    async def connect(self, websocket: WebSocket):
        await websocket.accept()
        self.active_connections.append(websocket)

    def disconnect(self, websocket: WebSocket):
        self.active_connections.remove(websocket)

    async def send_personal_message(self, message: str, websocket: WebSocket):
        await websocket.send_text(message)

    async def broadcast(self, message: str):
        for connection in self.active_connections:
            await connection.send_text(message)


# إنشاء مثيل لـ ConnectionManager لاستخدامه في أجزاء المشروع الأخرى
manager = ConnectionManager()


# تعريف دالة send_real_time_notification
async def send_real_time_notification(websocket: WebSocket, user_id: int, data: str):
    # مثال على كيفية إرسال إشعار في الوقت الحقيقي
    await manager.send_personal_message(f"User {user_id} says: {data}", websocket)
