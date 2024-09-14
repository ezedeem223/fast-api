from fastapi import BackgroundTasks, WebSocket
from fastapi_mail import FastMail, MessageSchema, ConnectionConfig
from pydantic import EmailStr
from typing import List
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


def send_email_notification(to: List[EmailStr], subject: str, body: str):
    """
    Send an email notification in the background.

    Args:
        to: List of recipient email addresses.
        subject: Subject of the email.
        body: Body of the email.
    """
    message = MessageSchema(
        subject=subject,
        recipients=to,
        body=body,
        subtype="html",
    )
    fm = FastMail(conf)
    fm.send_message(message)


def schedule_email_notification(
    background_tasks: BackgroundTasks, to: List[EmailStr], subject: str, body: str
):
    """
    Schedule the email notification to be sent in the background.

    Args:
        background_tasks: FastAPI's BackgroundTasks instance.
        to: List of recipient email addresses.
        subject: Subject of the email.
        body: Body of the email.
    """
    background_tasks.add_task(send_email_notification, to, subject, body)


# WebSocket connection management
class ConnectionManager:
    def __init__(self):
        self.active_connections: List[WebSocket] = []

    async def connect(self, websocket: WebSocket):
        """
        Accept a WebSocket connection and add it to the active connections list.

        Args:
            websocket: WebSocket connection to be accepted.
        """
        await websocket.accept()
        self.active_connections.append(websocket)

    def disconnect(self, websocket: WebSocket):
        """
        Remove a WebSocket connection from the active connections list.

        Args:
            websocket: WebSocket connection to be removed.
        """
        self.active_connections.remove(websocket)

    async def send_personal_message(self, message: str, websocket: WebSocket):
        """
        Send a personal message to a specific WebSocket connection.

        Args:
            message: Message to be sent.
            websocket: WebSocket connection to which the message will be sent.
        """
        await websocket.send_text(message)

    async def broadcast(self, message: str):
        """
        Broadcast a message to all active WebSocket connections.

        Args:
            message: Message to be broadcasted.
        """
        for connection in self.active_connections:
            await connection.send_text(message)


# Instance of ConnectionManager for usage across the project
manager = ConnectionManager()


# Define real-time notification function
async def send_real_time_notification(websocket: WebSocket, user_id: int, data: str):
    """
    Send a real-time notification to a WebSocket connection.

    Args:
        websocket: WebSocket connection to which the notification will be sent.
        user_id: ID of the user sending the message.
        data: Message content.
    """
    await manager.send_personal_message(f"User {user_id} says: {data}", websocket)
