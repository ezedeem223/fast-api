from fastapi import BackgroundTasks, WebSocket
from fastapi_mail import FastMail, MessageSchema, ConnectionConfig
from pydantic import EmailStr, ConfigDict
from typing import List, Union
from .config import settings

# Email configuration
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


class EmailNotification(MessageSchema):
    model_config = ConfigDict(from_attributes=True)


def send_email_notification(to: Union[str, List[str]], subject: str, body: str):
    """
    Send an email notification.

    Args:
        to: Recipient email address or list of addresses.
        subject: Subject of the email.
        body: Body of the email.
    """
    recipients = [to] if isinstance(to, str) else to
    message = EmailNotification(
        subject=subject,
        recipients=recipients,
        body=body,
        subtype="html",
    )
    fm = FastMail(conf)
    fm.send_message(message)


def schedule_email_notification(
    background_tasks: BackgroundTasks,
    to: Union[str, List[str]],
    subject: str,
    body: str,
):
    """
    Schedule the email notification to be sent in the background.

    Args:
        background_tasks: FastAPI's BackgroundTasks instance.
        to: Recipient email address or list of addresses.
        subject: Subject of the email.
        body: Body of the email.
    """
    background_tasks.add_task(send_email_notification, to, subject, body)


# WebSocket connection management
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


# Instance of ConnectionManager for usage across the project
manager = ConnectionManager()


# Define real-time notification function
async def send_real_time_notification(websocket: WebSocket, user_id: int, data: str):
    await manager.send_personal_message(f"User {user_id} says: {data}", websocket)
