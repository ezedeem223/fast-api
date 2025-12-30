"""Message router for direct/group messaging including media and legacy shims.

Auth required for all endpoints; integrates translation (Amenhotep AI), virus scanning
for uploads, and optional email notifications. Rate limits applied via limiter where
configured in middleware stack.
"""

from datetime import datetime
from typing import List, Optional

from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.middleware.rate_limit import limiter
from app.media_processing import scan_file_for_viruses as _scan_file_for_viruses
from app.notifications import queue_email_notification as _queue_email_notification
from app.notifications import (
    schedule_email_notification as _schedule_email_notification,
)
from app.services.messaging import MessageService
from fastapi import (
    APIRouter,
    BackgroundTasks,
    Depends,
    File,
    Form,
    Query,
    Request,
    Response,
    UploadFile,
    WebSocket,
    WebSocketDisconnect,
    status,
)

# Project modules
from .. import models, oauth2, schemas
from ..ai_chat.amenhotep import AmenhotepAI

router = APIRouter(prefix="/message", tags=["Messages"])


# ---------------------------------------------------
# Dependency
# ---------------------------------------------------


def get_message_service(db: Session = Depends(get_db)) -> MessageService:
    """Endpoint: get_message_service."""
    return MessageService(db)


# ---------------------------------------------------
# Compatibility helpers
# ---------------------------------------------------


def scan_file_for_viruses(file_path: str) -> bool:
    """Endpoint: scan_file_for_viruses."""
    return _scan_file_for_viruses(file_path)


def queue_email_notification(*args, **kwargs):
    """Endpoint: queue_email_notification."""
    return _queue_email_notification(*args, **kwargs)


def schedule_email_notification(*args, **kwargs):
    """Endpoint: schedule_email_notification."""
    return _schedule_email_notification(*args, **kwargs)


# ---------------------------------------------------
# API Endpoints
# ---------------------------------------------------


@router.post("/", status_code=status.HTTP_201_CREATED, response_model=schemas.Message)
@limiter.limit("60/minute")
async def create_message(
    request: Request,
    message: schemas.MessageCreate,
    background_tasks: BackgroundTasks,
    current_user: models.User = Depends(oauth2.get_current_user),
    service: MessageService = Depends(get_message_service),
):
    """
    Create a new message with optional file attachments or sticker.
    Validates recipient existence and block status, processes URLs for link previews,
    and handles post-creation tasks like logging and notifications.
    """
    return await service.create_message(
        payload=message, current_user=current_user, background_tasks=background_tasks
    )


@router.get("/", response_model=List[schemas.Message])
async def get_messages(
    current_user: models.User = Depends(oauth2.get_current_user),
    skip: int = 0,
    limit: int = 500,
    service: MessageService = Depends(get_message_service),
):
    """
    Retrieve messages for the current user.
    Marks received messages as read and translates content if needed.
    """
    return await service.list_messages(
        current_user=current_user, skip=skip, limit=limit
    )


@router.put("/{message_id}", response_model=schemas.Message)
@limiter.limit("30/hour")
async def update_message(
    request: Request,
    message_id: int,
    message_update: schemas.MessageUpdate,
    background_tasks: BackgroundTasks,
    current_user: models.User = Depends(oauth2.get_current_user),
    service: MessageService = Depends(get_message_service),
):
    """
    Update an existing message.
    Checks that the message exists, the current user is the sender,
    and the edit window has not expired.
    """
    return await service.update_message(
        message_id=message_id,
        payload=message_update,
        current_user=current_user,
        background_tasks=background_tasks,
    )


@router.delete("/{message_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_message(
    message_id: int,
    background_tasks: BackgroundTasks,
    current_user: models.User = Depends(oauth2.get_current_user),
    service: MessageService = Depends(get_message_service),
):
    """
    Delete an existing message.
    Verifies that the current user is the sender and the delete window has not expired.
    """
    await service.delete_message(
        message_id=message_id,
        current_user=current_user,
        background_tasks=background_tasks,
    )
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/conversations", response_model=List[schemas.Message])
async def get_conversations(
    current_user: models.User = Depends(oauth2.get_current_user),
    service: MessageService = Depends(get_message_service),
):
    """
    Retrieve the latest message from each conversation of the current user.
    """
    return await service.get_conversations(current_user=current_user)


@router.post("/location", response_model=schemas.Message)
@limiter.limit("30/hour")
async def send_location(
    request: Request,
    location: schemas.MessageCreate,
    current_user: models.User = Depends(oauth2.get_current_user),
    service: MessageService = Depends(get_message_service),
):
    """
    Send a location message.
    Requires latitude and longitude to be provided.
    """
    return await service.send_location(location=location, current_user=current_user)


@router.post("/audio", response_model=schemas.Message)
@limiter.limit("20/hour")
async def create_audio_message(
    request: Request,
    receiver_id: int,
    audio_file: UploadFile = File(...),
    duration: float = None,
    current_user: models.User = Depends(oauth2.get_current_user),
    service: MessageService = Depends(get_message_service),
):
    """
    Create an audio message.
    Validates the audio file extension and saves the file accordingly.
    """
    return await service.create_audio_message(
        receiver_id=receiver_id,
        audio_file=audio_file,
        duration=duration,
        current_user=current_user,
    )


@router.get("/unread", response_model=int)
async def get_unread_messages_count(
    current_user: models.User = Depends(oauth2.get_current_user),
    service: MessageService = Depends(get_message_service),
):
    """
    Retrieve the count of unread messages for the current user.
    """
    return await service.unread_count(current_user=current_user)


@router.get(
    "/statistics/{conversation_id}", response_model=schemas.ConversationStatistics
)
async def get_conversation_statistics(
    conversation_id: str,
    current_user: models.User = Depends(oauth2.get_current_user),
    service: MessageService = Depends(get_message_service),
):
    """
    Retrieve statistics for a specific conversation.
    """
    return await service.get_conversation_statistics(
        conversation_id=conversation_id, current_user=current_user
    )


@router.put("/{message_id}/read", response_model=schemas.Message)
async def mark_message_as_read(
    message_id: int,
    background_tasks: BackgroundTasks,
    current_user: models.User = Depends(oauth2.get_current_user),
    service: MessageService = Depends(get_message_service),
):
    """
    Mark a specific message as read.
    If the sender allows read status notifications, a real-time notification is sent.
    """
    return await service.mark_message_as_read(
        message_id=message_id,
        current_user=current_user,
        background_tasks=background_tasks,
    )


@router.post("/send_file", status_code=status.HTTP_201_CREATED)
@limiter.limit("15/hour")
async def send_file(
    request: Request,
    file: UploadFile = File(...),
    recipient_id: int = Form(...),
    current_user: models.User = Depends(oauth2.get_current_user),
    service: MessageService = Depends(get_message_service),
):
    """
    Send a file message.
    Validates file existence, size, and scans for viruses before saving.
    """
    return await service.send_file(
        file=file, recipient_id=recipient_id, current_user=current_user
    )


@router.get("/download/{file_name}")
async def download_file(
    file_name: str,
    current_user: models.User = Depends(oauth2.get_current_user),
    service: MessageService = Depends(get_message_service),
):
    """
    Download a file message.
    Validates that the current user is either the sender or receiver.
    """
    return await service.download_file(file_name=file_name, current_user=current_user)


@router.get("/inbox", response_model=List[schemas.MessageOut])
async def get_inbox(
    current_user: models.User = Depends(oauth2.get_current_user),
    skip: int = 0,
    limit: int = 100,
    service: MessageService = Depends(get_message_service),
):
    """
    Retrieve the inbox messages for the current user.
    """
    return await service.get_inbox(current_user=current_user, skip=skip, limit=limit)


@router.get("/search", response_model=schemas.MessageSearchResponse)
async def search_messages(
    query: Optional[str] = None,
    start_date: Optional[datetime] = None,
    end_date: Optional[datetime] = None,
    message_type: Optional[schemas.MessageType] = None,
    conversation_id: Optional[str] = None,
    sort_order: schemas.SortOrder = schemas.SortOrder.DESC,
    current_user: models.User = Depends(oauth2.get_current_user),
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=100),
    service: MessageService = Depends(get_message_service),
):
    """
    Search messages based on query, date range, message type, and conversation ID.
    """
    params = schemas.MessageSearch(
        query=query,
        start_date=start_date,
        end_date=end_date,
        message_type=message_type,
        conversation_id=conversation_id,
        sort_order=sort_order,
    )
    return await service.search_messages(
        params=params, current_user=current_user, skip=skip, limit=limit
    )


@router.get("/{message_id}", response_model=schemas.Message)
async def get_message(
    message_id: int,
    current_user: models.User = Depends(oauth2.get_current_user),
    service: MessageService = Depends(get_message_service),
):
    """
    Retrieve a specific message by its ID.
    """
    return await service.get_message(message_id=message_id, current_user=current_user)


@router.post(
    "/conversations",
    response_model=schemas.ConversationOut,
    status_code=status.HTTP_201_CREATED,
)
@limiter.limit("10/hour")
def create_conversation(
    request: Request,
    conversation: schemas.ConversationCreate,
    current_user: models.User = Depends(oauth2.get_current_user),
    service: MessageService = Depends(get_message_service),
):
    """
    Create a group conversation with the specified members.
    """
    return service.create_group_conversation(
        payload=conversation, current_user=current_user
    )


@router.get("/conversations", response_model=List[schemas.ConversationOut])
def list_conversations(
    current_user: models.User = Depends(oauth2.get_current_user),
    service: MessageService = Depends(get_message_service),
):
    """
    List conversations the current user belongs to.
    """
    return service.list_user_conversations(current_user=current_user)


@router.post(
    "/conversations/{conversation_id}/members",
    response_model=schemas.ConversationOut,
)
@limiter.limit("20/hour")
def add_conversation_members(
    request: Request,
    conversation_id: str,
    members_update: schemas.ConversationMembersUpdate,
    current_user: models.User = Depends(oauth2.get_current_user),
    service: MessageService = Depends(get_message_service),
):
    """
    Add members to an existing conversation.
    """
    return service.add_members_to_conversation(
        conversation_id=conversation_id,
        member_ids=members_update.member_ids,
        current_user=current_user,
    )


@router.delete(
    "/conversations/{conversation_id}/members/{user_id}",
    response_model=schemas.ConversationOut,
)
def remove_conversation_member(
    conversation_id: str,
    user_id: int,
    current_user: models.User = Depends(oauth2.get_current_user),
    service: MessageService = Depends(get_message_service),
):
    """
    Remove a member from the conversation.
    """
    return service.remove_member_from_conversation(
        conversation_id=conversation_id,
        user_id=user_id,
        current_user=current_user,
    )


@router.post(
    "/conversations/{conversation_id}/messages",
    response_model=schemas.Message,
    status_code=status.HTTP_201_CREATED,
)
@limiter.limit("60/minute")
async def send_group_message(
    request: Request,
    conversation_id: str,
    message: schemas.MessageCreate,
    background_tasks: BackgroundTasks,
    current_user: models.User = Depends(oauth2.get_current_user),
    service: MessageService = Depends(get_message_service),
):
    """
    Send a new message to a conversation.
    """
    payload_data = message.model_dump()
    payload_data["conversation_id"] = conversation_id
    payload_data.pop("receiver_id", None)
    group_payload = schemas.MessageCreate(**payload_data)
    return await service.send_group_message(
        conversation_id=conversation_id,
        payload=group_payload,
        current_user=current_user,
        background_tasks=background_tasks,
    )


@router.get(
    "/conversations/{conversation_id}/messages",
    response_model=List[schemas.Message],
)
async def get_conversation_messages(
    conversation_id: str,
    current_user: models.User = Depends(oauth2.get_current_user),
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=200),
    service: MessageService = Depends(get_message_service),
):
    """
    Retrieve messages for a given conversation.
    """
    return service.get_conversation_messages(
        conversation_id=conversation_id,
        current_user=current_user,
        skip=skip,
        limit=limit,
    )


@router.put("/user/read-status", response_model=schemas.UserOut)
async def update_read_status_visibility(
    user_update: schemas.UserUpdate,
    current_user: models.User = Depends(oauth2.get_current_user),
    service: MessageService = Depends(get_message_service),
):
    """
    Update the user's preference for read status visibility.
    """
    return await service.update_read_status_visibility(
        user_update=user_update, current_user=current_user
    )


@router.websocket("/ws/amenhotep/{user_id}")
async def amenhotep_chat(websocket: WebSocket, user_id: int):
    """Endpoint: amenhotep_chat."""
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
