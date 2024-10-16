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
)
from sqlalchemy.orm import Session
from sqlalchemy import or_, and_, func
from typing import List, Optional
from .. import models, schemas, oauth2, notifications, crypto
from ..database import get_db
from fastapi.responses import FileResponse
import clamd
import os
import re
from uuid import uuid4
from datetime import datetime, timedelta
import emoji
from ..link_preview import extract_link_preview


router = APIRouter(prefix="/message", tags=["Messages"])

AUDIO_DIR = "static/audio_messages"
os.makedirs(AUDIO_DIR, exist_ok=True)
EDIT_DELETE_WINDOW = 60
UPLOAD_DIR = "static/messages"


def generate_conversation_id(user1_id: int, user2_id: int) -> str:
    sorted_ids = sorted([user1_id, user2_id])
    return f"{sorted_ids[0]}_{sorted_ids[1]}"


@router.post("/", status_code=status.HTTP_201_CREATED, response_model=schemas.Message)
async def create_message(
    message: schemas.MessageCreate,
    files: List[UploadFile] = File(None),
    db: Session = Depends(get_db),
    current_user: models.User = Depends(oauth2.get_current_user),
    background_tasks: BackgroundTasks = BackgroundTasks(),
):
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

    block = (
        db.query(models.Block)
        .filter(
            models.Block.blocker_id == message.receiver_id,
            models.Block.blocked_id == current_user.id,
            models.Block.ends_at > datetime.now(),
        )
        .first()
    )
    if block and (
        block.block_type == models.BlockType.FULL
        or block.block_type == models.BlockType.PARTIAL_MESSAGE
    ):
        raise HTTPException(
            status_code=403, detail="You are blocked from sending messages to this user"
        )

    conversation_id = generate_conversation_id(current_user.id, message.receiver_id)
    new_message = models.Message(
        sender_id=current_user.id,
        receiver_id=message.receiver_id,
        conversation_id=conversation_id,
        content=message.content,
        message_type=schemas.MessageType.TEXT,
    )

    if message.content and emoji.emoji_count(message.content) > 0:
        new_message.has_emoji = True

    if files:
        new_message.message_type = schemas.MessageType.FILE
        for file in files:
            file_extension = os.path.splitext(file.filename)[1]
            unique_filename = f"{uuid.uuid4()}{file_extension}"
            file_path = os.path.join(UPLOAD_DIR, unique_filename)

            os.makedirs(os.path.dirname(file_path), exist_ok=True)

            with open(file_path, "wb") as buffer:
                buffer.write(await file.read())

            attachment = models.MessageAttachment(
                file_url=file_path, file_type=file.content_type
            )
            new_message.attachments.append(attachment)

        if all(file.content_type.startswith("image") for file in files):
            new_message.message_type = schemas.MessageType.IMAGE

    if message.sticker_id:
        sticker = (
            db.query(models.Sticker)
            .filter(
                models.Sticker.id == message.sticker_id, models.Sticker.approved == True
            )
            .first()
        )
        if not sticker:
            raise HTTPException(
                status_code=404, detail="Sticker not found or not approved"
            )
        new_message.sticker_id = sticker.id
        new_message.message_type = schemas.MessageType.STICKER

    urls = re.findall(
        r"http[s]?://(?:[a-zA-Z]|[0-9]|[$-_@.&+]|[!*\\(\\),]|(?:%[0-9a-fA-F][0-9a-fA-F]))+",
        message.content,
    )

    if urls:
        # استخدام مهمة خلفية لاستخراج معاينة الرابط
        background_tasks.add_task(update_link_preview, db, new_message.id, urls[0])

    db.add(new_message)
    db.commit()
    db.refresh(new_message)

    # تحديث إحصائيات المحادثة
    conversation_stats = (
        db.query(models.ConversationStatistics)
        .filter(models.ConversationStatistics.conversation_id == conversation_id)
        .first()
    )

    if not conversation_stats:
        conversation_stats = models.ConversationStatistics(
            conversation_id=conversation_id,
            user1_id=min(current_user.id, message.receiver_id),
            user2_id=max(current_user.id, message.receiver_id),
        )
        db.add(conversation_stats)

    conversation_stats.total_messages += 1
    conversation_stats.last_message_at = func.now()

    # تحديث إحصائيات إضافية
    if files:
        conversation_stats.total_files += len(files)
    if new_message.has_emoji:
        conversation_stats.total_emojis += 1
    if new_message.message_type == schemas.MessageType.STICKER:
        conversation_stats.total_stickers += 1

    # حساب متوسط وقت الرد
    last_message = (
        db.query(models.Message)
        .filter(
            models.Message.conversation_id == conversation_id,
            models.Message.id != new_message.id,
        )
        .order_by(models.Message.created_at.desc())
        .first()
    )

    if last_message:
        time_diff = (new_message.created_at - last_message.created_at).total_seconds()
        conversation_stats.total_response_time += time_diff
        conversation_stats.total_responses += 1
        conversation_stats.average_response_time = (
            conversation_stats.total_response_time / conversation_stats.total_responses
        )

    db.commit()

    return new_message


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


@router.get("/conversations", response_model=List[schemas.Message])
async def get_conversations(
    db: Session = Depends(get_db),
    current_user: models.User = Depends(oauth2.get_current_user),
):
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


@router.get("/", response_model=List[schemas.Message])
def get_messages(
    db: Session = Depends(get_db),
    current_user: models.User = Depends(oauth2.get_current_user),
    skip: int = 0,
    limit: int = 500,
):
    messages = (
        db.query(models.Message)
        .filter(
            (models.Message.sender_id == current_user.id)
            | (models.Message.receiver_id == current_user.id)
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

    db.commit()
    return messages


@router.get("/inbox", response_model=List[schemas.MessageOut])
def get_inbox(
    db: Session = Depends(get_db),
    current_user: models.User = Depends(oauth2.get_current_user),
    skip: int = 0,
    limit: int = 100,
):
    messages = (
        db.query(models.Message)
        .filter(models.Message.receiver_id == current_user.id)
        .order_by(models.Message.timestamp.desc())
        .offset(skip)
        .limit(limit)
        .all()
    )
    return [schemas.MessageOut(message=message, count=1) for message in messages]


@router.post("/send_file", status_code=status.HTTP_201_CREATED)
async def send_file(
    file: UploadFile = File(...),
    recipient_id: int = Form(...),
    db: Session = Depends(get_db),
    current_user: models.User = Depends(oauth2.get_current_user),
    background_tasks: BackgroundTasks = BackgroundTasks(),
):
    recipient = db.query(models.User).filter(models.User.id == recipient_id).first()
    if not recipient:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="User not found"
        )

    # Check if file is empty
    await file.seek(0)
    file_content = await file.read()
    await file.seek(0)  # Reset file pointer

    if len(file_content) == 0 or file.filename == "":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="File is empty"
        )

    file_size = len(file_content)

    if file_size > 10 * 1024 * 1024:  # 10MB
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail="File is too large",
        )

    file_location = f"static/messages/{file.filename}"

    os.makedirs(os.path.dirname(file_location), exist_ok=True)

    with open(file_location, "wb") as file_object:
        file_object.write(file_content)

    if not scan_file_for_viruses(file_location):
        os.remove(file_location)
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="File is infected with a virus.",
        )

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

    background_tasks.add_task(
        notifications.schedule_email_notification,
        to=recipient.email,
        subject="New File Received",
        body=f"You have received a file from {current_user.email}.",
    )

    return {"message": "File sent successfully"}


def scan_file_for_viruses(file_path: str) -> bool:
    cd = clamd.ClamdNetworkSocket()
    result = cd.scan(file_path)
    if result and result[file_path][0] == "FOUND":
        return False
    return True


@router.get("/download/{file_name}")
def download_file(
    file_name: str,
    current_user: models.User = Depends(oauth2.get_current_user),
    db: Session = Depends(get_db),
):
    message = (
        db.query(models.Message)
        .filter(models.Message.file_url == f"static/messages/{file_name}")
        .first()
    )
    if not message or (
        message.sender_id != current_user.id and message.receiver_id != current_user.id
    ):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="File not found"
        )

    file_path = f"static/messages/{file_name}"
    if not os.path.exists(file_path):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="File not found"
        )
    return FileResponse(path=file_path, filename=file_name)


@router.post(
    "/location", status_code=status.HTTP_201_CREATED, response_model=schemas.Message
)
def send_location(
    location: schemas.MessageCreate,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(oauth2.get_current_user),
):
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
    return new_message


@router.post(
    "/audio", status_code=status.HTTP_201_CREATED, response_model=schemas.Message
)
async def create_audio_message(
    receiver_id: int,
    audio_file: UploadFile = File(...),
    duration: float = None,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(oauth2.get_current_user),
):
    file_extension = os.path.splitext(audio_file.filename)[1]
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
    return new_message


@router.get("/{message_id}", response_model=schemas.Message)
def get_message(
    message_id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(oauth2.get_current_user),
):
    message = db.query(models.Message).filter(models.Message.id == message_id).first()
    if not message:
        raise HTTPException(status_code=404, detail="Message not found")

    if message.sender_id != current_user.id and message.receiver_id != current_user.id:
        raise HTTPException(
            status_code=403, detail="Not authorized to view this message"
        )

    return message


@router.put("/{message_id}", response_model=schemas.Message)
async def update_message(
    message_id: int,
    message_update: schemas.MessageUpdate,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(oauth2.get_current_user),
    background_tasks: BackgroundTasks = BackgroundTasks(),
):
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

    return message


@router.delete("/{message_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_message(
    message_id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(oauth2.get_current_user),
    background_tasks: BackgroundTasks = BackgroundTasks(),
):
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

    return {"detail": "Message deleted successfully"}


@router.put("/{message_id}/read", response_model=schemas.Message)
async def mark_message_as_read(
    message_id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(oauth2.get_current_user),
    background_tasks: BackgroundTasks = BackgroundTasks(),
):
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
        if not sender.hide_read_status:
            background_tasks.add_task(
                notifications.send_real_time_notification,
                sender.id,
                f"Message {message_id} has been read",
            )

    return message


@router.put("/user/read-status", response_model=schemas.User)
async def update_read_status_visibility(
    user_update: schemas.UserUpdate,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(oauth2.get_current_user),
):
    if user_update.hide_read_status is not None:
        current_user.hide_read_status = user_update.hide_read_status
        db.commit()
        db.refresh(current_user)

    return current_user


@router.get("/unread", response_model=int)
async def get_unread_messages_count(
    db: Session = Depends(get_db),
    current_user: models.User = Depends(oauth2.get_current_user),
):
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


def update_link_preview(db: Session, message_id: int, url: str):
    link_preview = extract_link_preview(url)
    if link_preview:
        db.query(models.Message).filter(models.Message.id == message_id).update(
            {"link_preview": link_preview}
        )
        db.commit()
