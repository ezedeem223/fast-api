from fastapi import BackgroundTasks, WebSocket
from fastapi_mail import FastMail, MessageSchema, ConnectionConfig
from pydantic import EmailStr, ConfigDict
from typing import List, Union
from .config import settings

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


async def send_email_notification(**kwargs):
    """
    Send an email notification.

    Keyword Args:
        to: Recipient email address or list of addresses.
        subject: Subject of the email.
        body: Body of the email.
    """
    recipients = kwargs.get("to")
    if isinstance(recipients, str):
        recipients = [recipients]

    message = EmailNotification(
        subject=kwargs.get("subject", ""),
        recipients=recipients,
        body=kwargs.get("body", ""),
        subtype="html",
    )
    fm = FastMail(conf)
    await fm.send_message(message)


async def schedule_email_notification(background_tasks: BackgroundTasks, **kwargs):
    """
    Schedule the email notification to be sent in the background.

    Args:
        background_tasks: FastAPI's BackgroundTasks instance.

    Keyword Args:
        to: Recipient email address or list of addresses.
        subject: Subject of the email.
        body: Body of the email.
    """
    background_tasks.add_task(send_email_notification, **kwargs)


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


manager = ConnectionManager()


async def send_real_time_notification(websocket: WebSocket, user_id: int, data: str):
    await manager.send_personal_message(f"User {user_id} says: {data}", websocket)


async def send_login_notification(email: str, ip_address: str, user_agent: str):
    subject = "New Login to Your Account"
    body = f"""
    We detected a new login to your account:
    
    IP Address: {ip_address}
    Device: {user_agent}
    
    If this wasn't you, please secure your account immediately.
    """
    await send_email_notification(to=email, subject=subject, body=body)


async def send_mention_notification(to: str, mentioner: str, post_id: int):
    subject = f"You've been mentioned by {mentioner}"
    body = (
        f"{mentioner} mentioned you in a post. Check it out: [link to post/{post_id}]"
    )
    await send_email_notification(to=to, subject=subject, body=body)


async def translate_notification_content(notification, user):
    notification.content = await get_translated_content(
        notification.content, user, notification.language
    )
    return notification


@router.get("/notifications", response_model=List[schemas.NotificationOut])
def get_user_notifications(
    db: Session = Depends(get_db),
    current_user: models.User = Depends(oauth2.get_current_user),
):
    notifications = (
        db.query(models.Notification)
        .filter(models.Notification.user_id == current_user.id)
        .order_by(models.Notification.created_at.desc())
        .all()
    )
    return notifications


@router.put("/notifications/{notification_id}/read")
def mark_notification_as_read(
    notification_id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(oauth2.get_current_user),
):
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
    notification.is_read = True
    db.commit()
    return {"message": "Notification marked as read"}
