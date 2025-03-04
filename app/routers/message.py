import os
import re
from uuid import uuid4
from datetime import datetime, timedelta, timezone

import emoji
import clamd

from typing import List, Optional

from fastapi import (
    APIRouter,
    Depends,
    HTTPException,
    status,
    UploadFile,
    File,
    BackgroundTasks,
    Form,
    Query,
    Response,
    WebSocket,
    WebSocketDisconnect,
)
from fastapi.responses import FileResponse

from sqlalchemy.orm import Session
from sqlalchemy import or_, and_, func

# Project modules
from .. import (
    models,
    schemas,
    oauth2,
    notifications,
    crypto,
)  # crypto imported for future use if needed
from ..database import get_db
from ..link_preview import extract_link_preview
from ..utils import (
    log_user_event,
    create_notification,
    detect_language,
    get_translated_content,
)
from ..analytics import update_conversation_statistics
from ..ai_chat.amenhotep import AmenhotepAI

# Constants and directory setup
AUDIO_DIR = "static/audio_messages"
os.makedirs(AUDIO_DIR, exist_ok=True)

UPLOAD_DIR = "static/messages"
os.makedirs(UPLOAD_DIR, exist_ok=True)

EDIT_DELETE_WINDOW = 60  # minutes allowed for editing/deleting messages
MAX_FILE_SIZE = 10 * 1024 * 1024  # 10MB maximum file size
ALLOWED_AUDIO_EXTENSIONS = {".mp3", ".wav", ".ogg", ".m4a"}

router = APIRouter(prefix="/message", tags=["Messages"])

# ---------------------------------------------------
# Utility Functions
# ---------------------------------------------------


def generate_conversation_id(user1_id: int, user2_id: int) -> str:
    """
    Generate a unique conversation ID for two users based on sorted user IDs.
    """
    sorted_ids = sorted([user1_id, user2_id])
    return f"{sorted_ids[0]}_{sorted_ids[1]}"


async def is_user_blocked(db: Session, blocker_id: int, blocked_id: int) -> bool:
    """
    Check if a user is blocked from sending messages.
    """
    block = (
        db.query(models.Block)
        .filter(
            models.Block.blocker_id == blocker_id,
            models.Block.blocked_id == blocked_id,
            models.Block.ends_at > datetime.now(),
        )
        .first()
    )
    return bool(
        block
        and block.block_type
        in [models.BlockType.FULL, models.BlockType.PARTIAL_MESSAGE]
    )


async def save_message_attachments(
    files: List[UploadFile], new_message: models.Message
):
    """
    Save file attachments for a message.
    Validates file size and stores the file with a unique name.
    """
    for file in files:
        file_content = await file.read()
        await file.seek(0)
        file_size = len(file_content)
        if file_size > MAX_FILE_SIZE:
            raise HTTPException(status_code=413, detail="File is too large")

        file_extension = os.path.splitext(file.filename)[1]
        unique_filename = f"{uuid4()}{file_extension}"
        file_path = os.path.join(UPLOAD_DIR, unique_filename)

        os.makedirs(os.path.dirname(file_path), exist_ok=True)
        with open(file_path, "wb") as buffer:
            buffer.write(await file.read())

        attachment = models.MessageAttachment(
            file_url=file_path, file_type=file.content_type
        )
        new_message.attachments.append(attachment)


async def get_valid_sticker(sticker_id: int, db: Session) -> Optional[models.Sticker]:
    """
    Retrieve a valid and approved sticker from the database.
    """
    return (
        db.query(models.Sticker)
        .filter(models.Sticker.id == sticker_id, models.Sticker.approved == True)
        .first()
    )


async def create_message_object(
    message: schemas.MessageCreate,
    current_user: models.User,
    files: List[UploadFile],
    db: Session,
) -> models.Message:
    """
    Create a new message object with attributes like sender, receiver, content,
    language detection, emoji flag, and message type based on attachments or sticker.
    """
    conversation_id = generate_conversation_id(current_user.id, message.receiver_id)
    new_message = models.Message(
        sender_id=current_user.id,
        receiver_id=message.receiver_id,
        conversation_id=conversation_id,
        content=message.content,
        message_type=schemas.MessageType.TEXT,
    )
    # Detect language and emoji presence
    new_message.language = detect_language(new_message.content)
    if message.content and emoji.emoji_count(message.content) > 0:
        new_message.has_emoji = True

    # Determine message type based on attachments
    if files:
        if all(file.content_type.startswith("image") for file in files):
            new_message.message_type = schemas.MessageType.IMAGE
        else:
            new_message.message_type = schemas.MessageType.FILE

    # Handle sticker if provided
    if message.sticker_id:
        sticker = await get_valid_sticker(message.sticker_id, db)
        if sticker:
            new_message.sticker_id = sticker.id
            new_message.message_type = schemas.MessageType.STICKER

    return new_message


async def handle_post_creation_tasks(
    message: models.Message,
    sender: models.User,
    recipient: models.User,
    db: Session,
    background_tasks: BackgroundTasks,
):
    """
    Handle post-message-creation tasks such as logging, updating statistics,
    creating notifications, and sending real-time notifications.
    """
    # Log user event
    log_user_event(db, sender.id, "send_message", {"receiver_id": recipient.id})
    # Update conversation statistics
    update_conversation_statistics(db, message.conversation_id, message)
    # Create a notification for the recipient
    create_notification(
        db,
        recipient.id,
        f"New message from {sender.username}",
        f"/messages/{sender.id}",
        "new_message",
        message.id,
    )
    # Send real-time notification in the background
    background_tasks.add_task(
        notifications.send_real_time_notification,
        recipient.id,
        f"New message from {sender.username}",
    )


def update_link_preview(db: Session, message_id: int, url: str):
    """
    Update a message with a link preview if available.
    """
    link_preview = extract_link_preview(url)
    if link_preview:
        db.query(models.Message).filter(models.Message.id == message_id).update(
            {"link_preview": link_preview}
        )
        db.commit()


def scan_file_for_viruses(file_path: str) -> bool:
    """
    Scan a file for viruses using ClamAV. Returns False if a virus is found.
    """
    cd = clamd.ClamdNetworkSocket()
    result = cd.scan(file_path)
    if result and result[file_path][0] == "FOUND":
        return False
    return True


# ---------------------------------------------------
# API Endpoints
# ---------------------------------------------------


@router.post("/", status_code=status.HTTP_201_CREATED, response_model=schemas.Message)
async def create_message(
    message: schemas.MessageCreate,
    files: List[UploadFile] = File(None),
    db: Session = Depends(get_db),
    current_user: models.User = Depends(oauth2.get_current_user),
    background_tasks: BackgroundTasks = BackgroundTasks(),
):
    """
    Create a new message with optional file attachments or sticker.
    Validates recipient existence and block status, processes URLs for link previews,
    and handles post-creation tasks like logging and notifications.
    """
    if not message.content and not files and not message.sticker_id:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Message must have content, files, or sticker",
        )

    recipient = (
        db.query(models.User).filter(models.User.id == message.receiver_id).first()
    )
    if not recipient:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Recipient not found"
        )

    if await is_user_blocked(db, message.receiver_id, current_user.id):
        raise HTTPException(
            status_code=403, detail="You are blocked from sending messages"
        )

    new_message = await create_message_object(message, current_user, files, db)

    # Process URLs in message content for link preview
    if message.content:
        urls = re.findall(
            r"http[s]?://(?:[a-zA-Z0-9/$-_@.&+!*\\(\\),]|(?:%[0-9a-fA-F][0-9a-fA-F]))+",
            message.content,
        )
        if urls:
            background_tasks.add_task(update_link_preview, db, new_message.id, urls[0])

    # Save attachments if provided
    if files:
        await save_message_attachments(files, new_message)

    db.add(new_message)
    db.commit()
    db.refresh(new_message)

    # Handle logging, notifications, and statistics update
    await handle_post_creation_tasks(
        new_message, current_user, recipient, db, background_tasks
    )

    # Translate message content if necessary
    new_message.content = await get_translated_content(
        new_message.content, current_user, new_message.language
    )

    return new_message


@router.get("/", response_model=List[schemas.Message])
async def get_messages(
    db: Session = Depends(get_db),
    current_user: models.User = Depends(oauth2.get_current_user),
    skip: int = 0,
    limit: int = 500,
):
    """
    Retrieve messages for the current user.
    Marks received messages as read and translates content if needed.
    """
    messages = (
        db.query(models.Message)
        .filter(
            or_(
                models.Message.sender_id == current_user.id,
                models.Message.receiver_id == current_user.id,
            )
        )
        .order_by(models.Message.timestamp.desc())
        .offset(skip)
        .limit(limit)
        .all()
    )

    for message in messages:
        if message.receiver_id == current_user.id and not message.is_read:
            message.is_read = True
            message.read_at = datetime.now()
        message.content = await get_translated_content(
            message.content, current_user, message.language
        )

    db.commit()
    return messages


@router.put("/{message_id}", response_model=schemas.Message)
async def update_message(
    message_id: int,
    message_update: schemas.MessageUpdate,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(oauth2.get_current_user),
    background_tasks: BackgroundTasks = BackgroundTasks(),
):
    """
    Update an existing message.
    Checks that the message exists, the current user is the sender,
    and the edit window has not expired.
    """
    message = db.query(models.Message).filter(models.Message.id == message_id).first()
    if not message:
        raise HTTPException(status_code=404, detail="Message not found")

    if message.sender_id != current_user.id:
        raise HTTPException(
            status_code=403, detail="Not authorized to edit this message"
        )

    time_difference = datetime.now(timezone.utc) - message.timestamp
    if time_difference > timedelta(minutes=EDIT_DELETE_WINDOW):
        raise HTTPException(status_code=400, detail="Edit window has expired")

    message.content = message_update.content
    message.is_edited = True
    db.commit()
    db.refresh(message)

    recipient = (
        db.query(models.User).filter(models.User.id == message.receiver_id).first()
    )
    background_tasks.add_task(
        notifications.send_real_time_notification,
        recipient.id,
        f"Message {message_id} has been edited",
    )
    create_notification(
        db,
        message.receiver_id,
        f"{current_user.username} edited a message",
        f"/messages/{current_user.id}",
        "message_edited",
        message.id,
    )

    return message


@router.delete("/{message_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_message(
    message_id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(oauth2.get_current_user),
    background_tasks: BackgroundTasks = BackgroundTasks(),
):
    """
    Delete an existing message.
    Verifies that the current user is the sender and the delete window has not expired.
    """
    message = db.query(models.Message).filter(models.Message.id == message_id).first()
    if not message:
        raise HTTPException(status_code=404, detail="Message not found")

    if message.sender_id != current_user.id:
        raise HTTPException(
            status_code=403, detail="Not authorized to delete this message"
        )

    time_difference = datetime.now(timezone.utc) - message.timestamp
    if time_difference > timedelta(minutes=EDIT_DELETE_WINDOW):
        raise HTTPException(status_code=400, detail="Delete window has expired")

    db.delete(message)
    db.commit()

    recipient = (
        db.query(models.User).filter(models.User.id == message.receiver_id).first()
    )
    background_tasks.add_task(
        notifications.send_real_time_notification,
        recipient.id,
        f"Message {message_id} has been deleted",
    )
    create_notification(
        db,
        message.receiver_id,
        f"{current_user.username} deleted a message",
        f"/messages/{current_user.id}",
        "message_deleted",
        None,
    )

    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/conversations", response_model=List[schemas.Message])
async def get_conversations(
    db: Session = Depends(get_db),
    current_user: models.User = Depends(oauth2.get_current_user),
):
    """
    Retrieve the latest message from each conversation of the current user.
    """
    subquery = (
        db.query(
            models.Message.conversation_id,
            func.max(models.Message.timestamp).label("last_message_time"),
        )
        .filter(
            or_(
                models.Message.sender_id == current_user.id,
                models.Message.receiver_id == current_user.id,
            )
        )
        .group_by(models.Message.conversation_id)
        .subquery()
    )

    conversations = (
        db.query(models.Message)
        .join(
            subquery,
            and_(
                models.Message.conversation_id == subquery.c.conversation_id,
                models.Message.timestamp == subquery.c.last_message_time,
            ),
        )
        .order_by(subquery.c.last_message_time.desc())
        .all()
    )

    return conversations


@router.post("/location", response_model=schemas.Message)
async def send_location(
    location: schemas.MessageCreate,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(oauth2.get_current_user),
):
    """
    Send a location message.
    Requires latitude and longitude to be provided.
    """
    if location.latitude is None or location.longitude is None:
        raise HTTPException(
            status_code=400, detail="Latitude and longitude are required"
        )

    new_message = models.Message(
        sender_id=current_user.id,
        receiver_id=location.receiver_id,
        latitude=location.latitude,
        longitude=location.longitude,
        is_current_location=location.is_current_location,
        location_name=location.location_name,
        content="Shared location",
        message_type=schemas.MessageType.TEXT,
    )
    db.add(new_message)
    db.commit()
    db.refresh(new_message)

    create_notification(
        db,
        location.receiver_id,
        f"{current_user.username} shared location",
        f"/messages/{current_user.id}",
        "shared_location",
        new_message.id,
    )

    return new_message


@router.post("/audio", response_model=schemas.Message)
async def create_audio_message(
    receiver_id: int,
    audio_file: UploadFile = File(...),
    duration: float = None,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(oauth2.get_current_user),
):
    """
    Create an audio message.
    Validates the audio file extension and saves the file accordingly.
    """
    file_extension = os.path.splitext(audio_file.filename)[1].lower()
    if file_extension not in ALLOWED_AUDIO_EXTENSIONS:
        raise HTTPException(status_code=400, detail="Unsupported audio format")

    file_name = f"{uuid4()}{file_extension}"
    file_path = os.path.join(AUDIO_DIR, file_name)

    with open(file_path, "wb") as buffer:
        content = await audio_file.read()
        buffer.write(content)

    new_message = models.Message(
        sender_id=current_user.id,
        receiver_id=receiver_id,
        audio_url=file_path,
        duration=duration,
        message_type=schemas.MessageType.FILE,
    )
    db.add(new_message)
    db.commit()
    db.refresh(new_message)

    create_notification(
        db,
        receiver_id,
        f"{current_user.username} sent an audio message",
        f"/messages/{current_user.id}",
        "new_audio_message",
        new_message.id,
    )

    return new_message


@router.get("/unread", response_model=int)
async def get_unread_messages_count(
    db: Session = Depends(get_db),
    current_user: models.User = Depends(oauth2.get_current_user),
):
    """
    Retrieve the count of unread messages for the current user.
    """
    unread_count = (
        db.query(models.Message)
        .filter(
            models.Message.receiver_id == current_user.id,
            models.Message.is_read == False,
        )
        .count()
    )
    return unread_count


@router.get(
    "/statistics/{conversation_id}", response_model=schemas.ConversationStatistics
)
async def get_conversation_statistics(
    conversation_id: str,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(oauth2.get_current_user),
):
    """
    Retrieve statistics for a specific conversation.
    """
    stats = (
        db.query(models.ConversationStatistics)
        .filter(
            models.ConversationStatistics.conversation_id == conversation_id,
            or_(
                models.ConversationStatistics.user1_id == current_user.id,
                models.ConversationStatistics.user2_id == current_user.id,
            ),
        )
        .first()
    )

    if not stats:
        raise HTTPException(status_code=404, detail="Conversation statistics not found")

    return stats


@router.put("/{message_id}/read", response_model=schemas.Message)
async def mark_message_as_read(
    message_id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(oauth2.get_current_user),
    background_tasks: BackgroundTasks = BackgroundTasks(),
):
    """
    Mark a specific message as read.
    If the sender allows read status notifications, a real-time notification is sent.
    """
    message = db.query(models.Message).filter(models.Message.id == message_id).first()
    if not message:
        raise HTTPException(status_code=404, detail="Message not found")

    if message.receiver_id != current_user.id:
        raise HTTPException(
            status_code=403, detail="Not authorized to mark this message as read"
        )

    if not message.is_read:
        message.is_read = True
        message.read_at = datetime.now(timezone.utc)
        db.commit()
        db.refresh(message)

        sender = (
            db.query(models.User).filter(models.User.id == message.sender_id).first()
        )
        if sender and not sender.hide_read_status:
            background_tasks.add_task(
                notifications.send_real_time_notification,
                sender.id,
                f"Message {message_id} has been read",
            )

    return message


@router.post("/send_file", status_code=status.HTTP_201_CREATED)
async def send_file(
    file: UploadFile = File(...),
    recipient_id: int = Form(...),
    db: Session = Depends(get_db),
    current_user: models.User = Depends(oauth2.get_current_user),
    background_tasks: BackgroundTasks = BackgroundTasks(),
):
    """
    Send a file message.
    Validates file existence, size, and scans for viruses before saving.
    """
    recipient = db.query(models.User).filter(models.User.id == recipient_id).first()
    if not recipient:
        raise HTTPException(status_code=404, detail="User not found")

    await file.seek(0)
    file_content = await file.read()
    await file.seek(0)

    if len(file_content) == 0 or file.filename == "":
        raise HTTPException(status_code=400, detail="File is empty")

    file_size = len(file_content)
    if file_size > MAX_FILE_SIZE:
        raise HTTPException(status_code=413, detail="File is too large")

    file_location = os.path.join(UPLOAD_DIR, file.filename)
    os.makedirs(os.path.dirname(file_location), exist_ok=True)

    with open(file_location, "wb") as file_object:
        file_object.write(file_content)

    # Scan for viruses using ClamAV
    if not scan_file_for_viruses(file_location):
        os.remove(file_location)
        raise HTTPException(status_code=400, detail="File is infected with a virus")

    new_message = models.Message(
        sender_id=current_user.id,
        receiver_id=recipient_id,
        content=file_location,
        message_type=schemas.MessageType.FILE,
        file_url=file_location,
    )
    db.add(new_message)
    db.commit()
    db.refresh(new_message)

    create_notification(
        db,
        recipient_id,
        f"New file from {current_user.username}",
        f"/messages/{current_user.id}",
        "new_file",
        new_message.id,
    )

    return {"message": "File sent successfully"}


@router.get("/download/{file_name}")
async def download_file(
    file_name: str,
    current_user: models.User = Depends(oauth2.get_current_user),
    db: Session = Depends(get_db),
):
    """
    Download a file message.
    Validates that the current user is either the sender or receiver.
    """
    file_path = os.path.join(UPLOAD_DIR, file_name)
    message = (
        db.query(models.Message).filter(models.Message.file_url == file_path).first()
    )
    if not message or (
        message.sender_id != current_user.id and message.receiver_id != current_user.id
    ):
        raise HTTPException(status_code=404, detail="File not found")
    if not os.path.exists(file_path):
        raise HTTPException(status_code=404, detail="File not found")
    return FileResponse(path=file_path, filename=file_name)


@router.get("/inbox", response_model=List[schemas.MessageOut])
async def get_inbox(
    db: Session = Depends(get_db),
    current_user: models.User = Depends(oauth2.get_current_user),
    skip: int = 0,
    limit: int = 100,
):
    """
    Retrieve the inbox messages for the current user.
    """
    messages = (
        db.query(models.Message)
        .filter(models.Message.receiver_id == current_user.id)
        .order_by(models.Message.timestamp.desc())
        .offset(skip)
        .limit(limit)
        .all()
    )
    return [schemas.MessageOut(message=message, count=1) for message in messages]


@router.get("/search", response_model=schemas.MessageSearchResponse)
async def search_messages(
    query: Optional[str] = None,
    start_date: Optional[datetime] = None,
    end_date: Optional[datetime] = None,
    message_type: Optional[schemas.MessageType] = None,
    conversation_id: Optional[str] = None,
    sort_order: schemas.SortOrder = schemas.SortOrder.DESC,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(oauth2.get_current_user),
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=100),
):
    """
    Search messages based on query, date range, message type, and conversation ID.
    """
    message_query = db.query(models.Message).filter(
        or_(
            models.Message.sender_id == current_user.id,
            models.Message.receiver_id == current_user.id,
        )
    )

    if query:
        message_query = message_query.filter(models.Message.content.ilike(f"%{query}%"))
    if start_date:
        message_query = message_query.filter(models.Message.timestamp >= start_date)
    if end_date:
        message_query = message_query.filter(models.Message.timestamp <= end_date)
    if message_type:
        message_query = message_query.filter(
            models.Message.message_type == message_type
        )
    if conversation_id:
        message_query = message_query.filter(
            models.Message.conversation_id == conversation_id
        )

    total = message_query.count()

    if sort_order == schemas.SortOrder.ASC:
        message_query = message_query.order_by(models.Message.timestamp.asc())
    else:
        message_query = message_query.order_by(models.Message.timestamp.desc())

    messages = message_query.offset(skip).limit(limit).all()
    return schemas.MessageSearchResponse(total=total, messages=messages)


@router.get("/{message_id}", response_model=schemas.Message)
async def get_message(
    message_id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(oauth2.get_current_user),
):
    """
    Retrieve a specific message by its ID.
    """
    message = db.query(models.Message).filter(models.Message.id == message_id).first()
    if not message:
        raise HTTPException(status_code=404, detail="Message not found")
    if message.sender_id != current_user.id and message.receiver_id != current_user.id:
        raise HTTPException(
            status_code=403, detail="Not authorized to view this message"
        )
    return message


@router.put("/user/read-status", response_model=schemas.User)
async def update_read_status_visibility(
    user_update: schemas.UserUpdate,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(oauth2.get_current_user),
):
    """
    Update the user's preference for read status visibility.
    """
    if user_update.hide_read_status is not None:
        current_user.hide_read_status = user_update.hide_read_status
        db.commit()
        db.refresh(current_user)
    return current_user


@router.websocket("/ws/amenhotep/{user_id}")
async def amenhotep_chat(websocket: WebSocket, user_id: int):
    """
    WebSocket endpoint for Amenhotep AI chat.
    Accepts the connection, sends a welcome message, and processes user messages
    to return responses generated by the Amenhotep AI.
    """
    await websocket.accept()
    amenhotep = AmenhotepAI()
    # Send welcome message
    await websocket.send_text(amenhotep.get_welcome_message())
    try:
        while True:
            # Receive message from the user
            message = await websocket.receive_text()
            # Get response from Amenhotep AI
            response_text = await amenhotep.get_response(message)
            # Send the response back to the user
            await websocket.send_text(response_text)
    except WebSocketDisconnect:
        print(f"User {user_id} disconnected from Amenhotep chat")
