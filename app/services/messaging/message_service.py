"""Service layer encapsulating messaging workflows with legacy shims and media handling."""

from __future__ import annotations

import asyncio
import os
import re
from datetime import datetime, timedelta, timezone
from pathlib import Path
from http import HTTPStatus
from typing import List, Optional
from uuid import uuid4

import emoji
from fastapi import BackgroundTasks, HTTPException, UploadFile, status
from fastapi.responses import FileResponse
from sqlalchemy import and_, func, or_
from sqlalchemy.orm import Session, joinedload

from app import models, notifications, schemas
from app.analytics import update_conversation_statistics
from app.core.database import get_db  # noqa: F401 - imported for typing parity
from app.notifications import (
    create_notification,
    queue_email_notification as _queue_email_notification_direct,
    schedule_email_notification as _schedule_email_notification_direct,
)
from app.modules.utils.content import detect_language
from app.modules.utils.translation import get_translated_content
from app.modules.utils.common import get_user_display_name
from app.modules.utils.events import log_user_event
from app.modules.utils.links import update_link_preview as legacy_update_link_preview

HTTP_422_UNPROCESSABLE_CONTENT = getattr(
    status, "HTTP_422_UNPROCESSABLE_CONTENT", HTTPStatus.UNPROCESSABLE_ENTITY
)

class MessageService:
    """Encapsulates all message CRUD operations and helper workflows."""

    EDIT_DELETE_WINDOW = 60  # minutes
    MAX_FILE_SIZE = 10 * 1024 * 1024
    ALLOWED_AUDIO_EXTENSIONS = {".mp3", ".wav", ".ogg", ".m4a"}
    UPLOAD_DIR = Path("static/messages")
    AUDIO_DIR = Path("static/audio_messages")

    def __init__(self, db: Session):
        self.db = db
        # Pre-create upload roots so background tasks/readers never hit missing dirs.
        self.UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
        self.AUDIO_DIR.mkdir(parents=True, exist_ok=True)

    # ------------------------------------------------------------------ helpers
    def _get_conversation_or_404(self, conversation_id: str) -> models.Conversation:
        conversation = (
            self.db.query(models.Conversation)
            .filter(
                models.Conversation.id == conversation_id,
                models.Conversation.is_active.is_(True),
            )
            .options(joinedload(models.Conversation.members))
            .first()
        )
        if not conversation:
            raise HTTPException(status_code=404, detail="Conversation not found")
        return conversation

    def _ensure_conversation_membership(self, conversation_id: str, user_id: int) -> None:
        member = (
            self.db.query(models.ConversationMember)
            .filter(
                models.ConversationMember.conversation_id == conversation_id,
                models.ConversationMember.user_id == user_id,
            )
            .first()
        )
        if not member:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="You are not part of this conversation",
            )

    def _ensure_conversation_manager(self, conversation_id: str, user_id: int) -> None:
        member = (
            self.db.query(models.ConversationMember)
            .filter(
                models.ConversationMember.conversation_id == conversation_id,
                models.ConversationMember.user_id == user_id,
            )
            .first()
        )
        if not member or member.role == models.ConversationMemberRole.MEMBER:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Only conversation owners or admins can modify membership",
            )

    def _get_conversation_members(
        self, conversation_id: str, *, exclude_user_id: Optional[int] = None
    ) -> List[models.User]:
        query = (
            self.db.query(models.User)
            .join(
                models.ConversationMember,
                models.ConversationMember.user_id == models.User.id,
            )
            .filter(models.ConversationMember.conversation_id == conversation_id)
        )
        if exclude_user_id is not None:
            query = query.filter(models.User.id != exclude_user_id)
        return query.all()

    def _get_or_create_direct_conversation(
        self, user_a: int, user_b: int
    ) -> str:
        conversation_id = self._conversation_id(user_a, user_b)
        conversation = (
            self.db.query(models.Conversation)
            .filter(models.Conversation.id == conversation_id)
            .first()
        )
        if not conversation:
            conversation = models.Conversation(
                id=conversation_id,
                type=models.ConversationType.DIRECT,
                created_by=user_a,
            )
            self.db.add(conversation)
            self.db.flush()
            for uid in {user_a, user_b}:
                member = models.ConversationMember(
                    conversation_id=conversation_id,
                    user_id=uid,
                    role=(
                        models.ConversationMemberRole.OWNER
                        if uid == user_a
                        else models.ConversationMemberRole.MEMBER
                    ),
                )
                self.db.add(member)
            self.db.commit()
        return conversation_id

    @staticmethod
    def _conversation_id(user1_id: int, user2_id: int) -> str:
        return f"{min(user1_id, user2_id)}_{max(user1_id, user2_id)}"

    async def _is_user_blocked(self, blocker_id: int, blocked_id: int) -> bool:
        block = (
            self.db.query(models.Block)
            .filter(
                models.Block.blocker_id == blocker_id,
                models.Block.blocked_id == blocked_id,
                or_(
                models.Block.ends_at.is_(None),
                    models.Block.ends_at > datetime.now(),
                ),
            )
            .first()
        )
        return bool(
            block
            and block.block_type
            in [models.BlockType.FULL, models.BlockType.PARTIAL_MESSAGE]
        )

    async def _save_message_attachments(
        self, files: List[UploadFile], new_message: models.Message
    ):
        for file in files:
            file_content = await file.read()
            await file.seek(0)
            if len(file_content) > self.MAX_FILE_SIZE:
                raise HTTPException(status_code=413, detail="File is too large")

            file_extension = os.path.splitext(file.filename)[1]
            unique_filename = f"{uuid4()}{file_extension}"
            file_path = self.UPLOAD_DIR / unique_filename
            file_path.parent.mkdir(parents=True, exist_ok=True)
            with open(file_path, "wb") as buffer:
                buffer.write(file_content)

            attachment = models.MessageAttachment(
                file_url=str(file_path), file_type=file.content_type
            )
            new_message.attachments.append(attachment)

    def _get_valid_sticker(self, sticker_id: int) -> Optional[models.Sticker]:
        return (
            self.db.query(models.Sticker)
            .filter(models.Sticker.id == sticker_id, models.Sticker.approved.is_(True))
            .first()
        )

    async def _create_message_object(
        self,
        payload: schemas.MessageCreate,
        current_user: models.User,
        content_text: str,
        files: Optional[List[UploadFile]] = None,
        conversation_id: Optional[str] = None,
        receiver_id: Optional[int] = None,
    ) -> models.Message:
        target_receiver = receiver_id or payload.receiver_id
        if conversation_id:
            conversation_key = conversation_id
        else:
            if not target_receiver:
                raise HTTPException(
                    status_code=HTTP_422_UNPROCESSABLE_CONTENT,
                    detail="Receiver is required for direct messages",
                )
            conversation_key = self._conversation_id(
                current_user.id, target_receiver
            )
        normalized_content = content_text or None

        encrypted_payload = payload.encrypted_content
        if encrypted_payload is None:
            encrypted_payload = (content_text or "").encode("utf-8")
        elif isinstance(encrypted_payload, str):
            encrypted_payload = encrypted_payload.encode("utf-8")
        else:
            encrypted_payload = bytes(encrypted_payload)

        message_type = payload.message_type or schemas.MessageType.TEXT

        new_message = models.Message(
            sender_id=current_user.id,
            receiver_id=target_receiver,
            conversation_id=conversation_key,
            content=normalized_content,
            encrypted_content=encrypted_payload,
            message_type=message_type,
        )

        try:
            new_message.language = (
                detect_language(content_text) if content_text else "unknown"
            )
        except Exception:
            new_message.language = "unknown"

        now = datetime.now(timezone.utc)
        new_message.timestamp = now
        setattr(new_message, "created_at", now)
        setattr(
            new_message,
            "has_emoji",
            bool(content_text and emoji.emoji_count(content_text) > 0),
        )

        if files:
            await self._save_message_attachments(files, new_message)
            if all(file.content_type.startswith("image") for file in files):
                new_message.message_type = schemas.MessageType.IMAGE
            else:
                new_message.message_type = schemas.MessageType.FILE

        if payload.sticker_id:
            sticker = self._get_valid_sticker(payload.sticker_id)
            if not sticker:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail="Sticker not found or not approved",
                )
            new_message.sticker_id = sticker.id
            new_message.message_type = schemas.MessageType.STICKER

        return new_message

    async def _handle_post_creation_tasks(
        self,
        message: models.Message,
        sender: models.User,
        recipients: List[models.User],
        background_tasks: BackgroundTasks,
    ):
        if not recipients:
            return
        sender_display = get_user_display_name(sender)
        log_user_event(self.db, sender.id, "send_message", {"conversation_id": message.conversation_id})
        update_conversation_statistics(self.db, message.conversation_id, message)
        for recipient in recipients:
            create_notification(
                self.db,
                recipient.id,
                f"New message from {sender_display}",
                f"/messages/{sender.id}",
                "new_message",
                message.id,
            )
            self._queue_email_notification(
                background_tasks,
                to=recipient.email,
                subject="New Message Received",
                body=f"You have received a new message from {sender.email}.",
            )
            self._schedule_email_notification(
                background_tasks,
                to=recipient.email,
                subject="New Message Received",
                body=f"You have received a new message from {sender.email}.",
            )
            realtime_payload = f"New message from {sender.email}: {message.content or ''}"
            realtime_target = f"/ws/{recipient.id}"
            personal_message = notifications.manager.send_personal_message
            if asyncio.iscoroutinefunction(personal_message):
                background_tasks.add_task(
                    asyncio.run, personal_message(realtime_payload, realtime_target)
                )
            else:
                background_tasks.add_task(
                    personal_message, realtime_payload, realtime_target
                )

    def _schedule_link_preview(
        self, background_tasks: BackgroundTasks, message_id: int, url: str
    ):
        # Run link preview out of band to avoid blocking the send path.
        background_tasks.add_task(legacy_update_link_preview, self.db, message_id, url)

    @staticmethod
    def _queue_email_notification(*args, **kwargs):
        try:
            from app.routers import message as message_router

            if hasattr(message_router, "queue_email_notification"):
                return message_router.queue_email_notification(*args, **kwargs)
        except Exception:  # pragma: no cover
            pass

        return _queue_email_notification_direct(*args, **kwargs)

    @staticmethod
    def _schedule_email_notification(*args, **kwargs):
        try:
            from app.routers import message as message_router

            if hasattr(message_router, "schedule_email_notification"):
                return message_router.schedule_email_notification(*args, **kwargs)
        except Exception:  # pragma: no cover
            pass

        return _schedule_email_notification_direct(*args, **kwargs)

    @staticmethod
    def _scan_file_for_viruses(file_path: str) -> bool:
        """Use the router shim (patched in tests) or fall back to media helper."""
        try:
            from app.routers import message as message_router

            if hasattr(message_router, "scan_file_for_viruses"):
                return message_router.scan_file_for_viruses(file_path)
        except Exception:  # pragma: no cover - defensive import for early startup
            pass

        from app.media_processing import scan_file_for_viruses as media_scan

        return media_scan(file_path)

    # ---------------------------------------------------------------- operations
    async def create_message(
        self,
        *,
        payload: schemas.MessageCreate,
        current_user: models.User,
        background_tasks: BackgroundTasks,
    ) -> models.Message:
        content_text = (payload.content or "").strip() if payload.content else ""
        if content_text and len(content_text) > 1000:
            raise HTTPException(
                status_code=HTTP_422_UNPROCESSABLE_CONTENT,
                detail="Message content exceeds the maximum length of 1000 characters",
            )
        if not content_text and not payload.sticker_id:
            raise HTTPException(
                status_code=HTTP_422_UNPROCESSABLE_CONTENT,
                detail="Message content cannot be empty",
            )
        if payload.receiver_id is None:
            raise HTTPException(
                status_code=HTTP_422_UNPROCESSABLE_CONTENT,
                detail="receiver_id is required for direct messages",
            )

        recipient = (
            self.db.query(models.User)
            .filter(models.User.id == payload.receiver_id)
            .first()
        )
        if not recipient:
            raise HTTPException(status_code=422, detail="User not found")

        if await self._is_user_blocked(payload.receiver_id, current_user.id):
            raise HTTPException(
                status_code=422, detail="You can't send messages to this user"
            )

        conversation_id = self._get_or_create_direct_conversation(
            current_user.id, recipient.id
        )
        new_message = await self._create_message_object(
            payload,
            current_user,
            content_text,
            conversation_id=conversation_id,
            receiver_id=recipient.id,
        )

        urls: List[str] = []
        if content_text:
            urls = re.findall(
                r"http[s]?://(?:[a-zA-Z0-9/$-_@.&+!*\\(\\),]|(?:%[0-9a-fA-F][0-9a-fA-F]))+",
                content_text,
            )

        self.db.add(new_message)
        self.db.flush()
        if urls:
            self._schedule_link_preview(background_tasks, new_message.id, urls[0])

        conversation = self._get_conversation_or_404(conversation_id)
        conversation.last_message_at = datetime.now(timezone.utc)

        self.db.commit()
        self.db.refresh(new_message)

        await self._handle_post_creation_tasks(
            new_message, current_user, [recipient], background_tasks
        )

        new_message.content = await get_translated_content(
            new_message.content, current_user, new_message.language
        )
        return new_message

    async def send_group_message(
        self,
        *,
        conversation_id: str,
        payload: schemas.MessageCreate,
        current_user: models.User,
        background_tasks: BackgroundTasks,
    ) -> models.Message:
        conversation = self._get_conversation_or_404(conversation_id)
        self._ensure_conversation_membership(conversation_id, current_user.id)
        content_text = (payload.content or "").strip() if payload.content else ""
        if content_text and len(content_text) > 1000:
            raise HTTPException(
                status_code=HTTP_422_UNPROCESSABLE_CONTENT,
                detail="Message content exceeds the maximum length of 1000 characters",
            )
        if not content_text and not payload.sticker_id:
            raise HTTPException(
                status_code=HTTP_422_UNPROCESSABLE_CONTENT,
                detail="Message content cannot be empty",
            )

        recipients = self._get_conversation_members(
            conversation_id, exclude_user_id=current_user.id
        )
        if not recipients:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Conversation has no other members",
            )

        new_message = await self._create_message_object(
            payload,
            current_user,
            content_text,
            conversation_id=conversation_id,
            receiver_id=None,
        )

        urls: List[str] = []
        if content_text:
            urls = re.findall(
                r"http[s]?://(?:[a-zA-Z0-9/$-_@.&+!*\\(\\),]|(?:%[0-9a-fA-F][0-9a-fA-F]))+",
                content_text,
            )

        self.db.add(new_message)
        self.db.flush()
        if urls:
            self._schedule_link_preview(background_tasks, new_message.id, urls[0])

        conversation.last_message_at = datetime.now(timezone.utc)
        self.db.commit()
        self.db.refresh(new_message)

        await self._handle_post_creation_tasks(
            new_message, current_user, recipients, background_tasks
        )
        new_message.content = await get_translated_content(
            new_message.content, current_user, new_message.language
        )
        return new_message

    async def list_messages(
        self, *, current_user: models.User, skip: int, limit: int
    ) -> List[models.Message]:
        messages = (
            self.db.query(models.Message)
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
        self.db.commit()
        return messages

    async def update_message(
        self,
        *,
        message_id: int,
        payload: schemas.MessageUpdate,
        current_user: models.User,
        background_tasks: BackgroundTasks,
    ) -> models.Message:
        message = (
            self.db.query(models.Message).filter(models.Message.id == message_id).first()
        )
        if not message:
            raise HTTPException(status_code=404, detail="Message not found")
        if message.sender_id != current_user.id:
            raise HTTPException(status_code=403, detail="Not authorized to edit this message")

        msg_ts = message.timestamp
        if msg_ts.tzinfo is None:
            msg_ts = msg_ts.replace(tzinfo=timezone.utc)

        now = datetime.now(timezone.utc)
        if getattr(now, "tzinfo", None) is None:
            now = now.replace(tzinfo=timezone.utc)

        if now - msg_ts > timedelta(
            minutes=self.EDIT_DELETE_WINDOW
        ):
            raise HTTPException(status_code=400, detail="Edit window has expired")

        message.content = payload.content
        message.is_edited = True
        self.db.commit()
        self.db.refresh(message)

        recipient = (
            self.db.query(models.User).filter(models.User.id == message.receiver_id).first()
        )
        background_tasks.add_task(
            notifications.send_real_time_notification,
            recipient.id,
            f"Message {message_id} has been edited",
        )
        editor_name = get_user_display_name(current_user)
        create_notification(
            self.db,
            message.receiver_id,
            f"{editor_name} edited a message",
            f"/messages/{current_user.id}",
            "message_edited",
            message.id,
        )
        return message

    async def delete_message(
        self,
        *,
        message_id: int,
        current_user: models.User,
        background_tasks: BackgroundTasks,
    ) -> None:
        message = (
            self.db.query(models.Message).filter(models.Message.id == message_id).first()
        )
        if not message:
            raise HTTPException(status_code=404, detail="Message not found")
        if message.sender_id != current_user.id:
            raise HTTPException(status_code=403, detail="Not authorized to delete this message")
        msg_ts = message.timestamp
        if msg_ts.tzinfo is None:
            msg_ts = msg_ts.replace(tzinfo=timezone.utc)

        now = datetime.now(timezone.utc)
        if getattr(now, "tzinfo", None) is None:
            now = now.replace(tzinfo=timezone.utc)

        if now - msg_ts > timedelta(
            minutes=self.EDIT_DELETE_WINDOW
        ):
            raise HTTPException(status_code=400, detail="Delete window has expired")

        recipient = (
            self.db.query(models.User).filter(models.User.id == message.receiver_id).first()
        )
        self.db.delete(message)
        self.db.commit()

        background_tasks.add_task(
            notifications.send_real_time_notification,
            recipient.id,
            f"Message {message_id} has been deleted",
        )
        deleter_name = get_user_display_name(current_user)
        create_notification(
            self.db,
            message.receiver_id,
            f"{deleter_name} deleted a message",
            f"/messages/{current_user.id}",
            "message_deleted",
            None,
        )

    async def get_conversations(self, *, current_user: models.User) -> List[models.Message]:
        subquery = (
            self.db.query(
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
            self.db.query(models.Message)
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

    async def send_location(
        self,
        *,
        location: schemas.MessageCreate,
        current_user: models.User,
    ) -> models.Message:
        if location.latitude is None or location.longitude is None:
            raise HTTPException(status_code=400, detail="Latitude and longitude are required")

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
        self.db.add(new_message)
        self.db.commit()
        self.db.refresh(new_message)

        sender_name = get_user_display_name(current_user)
        create_notification(
            self.db,
            location.receiver_id,
            f"{sender_name} shared location",
            f"/messages/{current_user.id}",
            "shared_location",
            new_message.id,
        )
        return new_message

    async def create_audio_message(
        self,
        *,
        receiver_id: int,
        audio_file: UploadFile,
        duration: Optional[float],
        current_user: models.User,
    ) -> models.Message:
        file_extension = os.path.splitext(audio_file.filename)[1].lower()
        if file_extension not in self.ALLOWED_AUDIO_EXTENSIONS:
            raise HTTPException(status_code=400, detail="Unsupported audio format")

        file_name = f"{uuid4()}{file_extension}"
        file_path = self.AUDIO_DIR / file_name
        with open(file_path, "wb") as buffer:
            content = await audio_file.read()
            buffer.write(content)

        new_message = models.Message(
            sender_id=current_user.id,
            receiver_id=receiver_id,
            audio_url=str(file_path),
            duration=duration,
            message_type=schemas.MessageType.FILE,
        )
        self.db.add(new_message)
        attachment = models.MessageAttachment(
            message=new_message, file_url=str(file_path), file_type=audio_file.content_type or "audio"
        )
        self.db.add(attachment)
        self.db.commit()
        self.db.refresh(new_message)

        sender_name = get_user_display_name(current_user)
        create_notification(
            self.db,
            receiver_id,
            f"{sender_name} sent an audio message",
            f"/messages/{current_user.id}",
            "new_audio_message",
            new_message.id,
        )
        update_conversation_statistics(self.db, new_message.conversation_id, new_message)
        return new_message

    async def unread_count(self, *, current_user: models.User) -> int:
        return (
            self.db.query(models.Message)
            .filter(
                models.Message.receiver_id == current_user.id,
                models.Message.is_read.is_(False),
            )
            .count()
        )

    async def get_conversation_statistics(
        self, *, conversation_id: str, current_user: models.User
    ) -> models.ConversationStatistics:
        stats = (
            self.db.query(models.ConversationStatistics)
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

    async def mark_message_as_read(
        self,
        *,
        message_id: int,
        current_user: models.User,
        background_tasks: BackgroundTasks,
    ) -> models.Message:
        message = (
            self.db.query(models.Message).filter(models.Message.id == message_id).first()
        )
        if not message:
            raise HTTPException(status_code=404, detail="Message not found")
        if message.receiver_id != current_user.id:
            raise HTTPException(status_code=403, detail="Not authorized to mark this message as read")
        if not message.is_read:
            message.is_read = True
            message.read_at = datetime.now(timezone.utc)
            self.db.commit()
            self.db.refresh(message)

            sender = (
                self.db.query(models.User).filter(models.User.id == message.sender_id).first()
            )
            if sender and not sender.hide_read_status:
                background_tasks.add_task(
                    notifications.send_real_time_notification,
                    sender.id,
                    f"Message {message_id} has been read",
                )
        return message

    async def send_file(
        self,
        *,
        file: UploadFile,
        recipient_id: int,
        current_user: models.User,
    ) -> dict:
        recipient = (
            self.db.query(models.User).filter(models.User.id == recipient_id).first()
        )
        if not recipient:
            raise HTTPException(status_code=404, detail="User not found")

        await file.seek(0)
        file_content = await file.read()
        await file.seek(0)
        if len(file_content) == 0 or file.filename == "":
            raise HTTPException(status_code=400, detail="File is empty")
        if len(file_content) > self.MAX_FILE_SIZE:
            raise HTTPException(status_code=413, detail="File is too large")

        # Ensure a conversation row exists to satisfy FK constraints
        conversation_id = self._get_or_create_direct_conversation(
            current_user.id, recipient_id
        )

        file_location = self.UPLOAD_DIR / file.filename
        file_location.parent.mkdir(parents=True, exist_ok=True)
        with open(file_location, "wb") as file_object:
            file_object.write(file_content)

        if not self._scan_file_for_viruses(str(file_location)):
            os.remove(file_location)
            raise HTTPException(status_code=400, detail="File is infected with a virus")

        new_message = models.Message(
            sender_id=current_user.id,
            receiver_id=recipient_id,
            content=str(file_location),
            encrypted_content=file_content,
            message_type=schemas.MessageType.FILE,
            file_url=str(file_location),
            conversation_id=conversation_id,
        )
        self.db.add(new_message)
        attachment = models.MessageAttachment(
            message=new_message, file_url=str(file_location), file_type=file.content_type or "file"
        )
        self.db.add(attachment)
        self.db.commit()
        self.db.refresh(new_message)

        sender_display = get_user_display_name(current_user)
        create_notification(
            self.db,
            recipient_id,
            f"New file from {sender_display}",
            f"/messages/{current_user.id}",
            "new_file",
            new_message.id,
        )
        update_conversation_statistics(self.db, conversation_id, new_message)
        return {"message": "File sent successfully"}

    async def download_file(
        self,
        *,
        file_name: str,
        current_user: models.User,
    ) -> FileResponse:
        file_path = self.UPLOAD_DIR / file_name
        message = (
            self.db.query(models.Message)
            .filter(models.Message.file_url == str(file_path))
            .first()
        )
        if not message or (
            message.sender_id != current_user.id
            and message.receiver_id != current_user.id
        ):
            raise HTTPException(status_code=404, detail="File not found")
        if not file_path.exists():
            raise HTTPException(status_code=404, detail="File not found")
        return FileResponse(path=str(file_path), filename=file_name)

    def create_group_conversation(
        self, *, payload: schemas.ConversationCreate, current_user: models.User
    ) -> models.Conversation:
        member_ids = set(payload.member_ids or [])
        member_ids.discard(current_user.id)
        if member_ids:
            existing = {
                row[0]
                for row in self.db.query(models.User.id).filter(models.User.id.in_(member_ids)).all()
            }
            missing = member_ids - existing
            if missing:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"Invalid member ids: {sorted(missing)}",
                )
        conversation = models.Conversation(
            id=str(uuid4()),
            title=payload.title,
            type=models.ConversationType.GROUP,
            created_by=current_user.id,
        )
        self.db.add(conversation)
        self.db.flush()
        all_members = {current_user.id} | member_ids
        for uid in all_members:
            role = (
                models.ConversationMemberRole.OWNER
                if uid == current_user.id
                else models.ConversationMemberRole.MEMBER
            )
            self.db.add(
                models.ConversationMember(
                    conversation_id=conversation.id,
                    user_id=uid,
                    role=role,
                )
            )
        self.db.commit()
        self.db.refresh(conversation)
        return conversation

    def list_user_conversations(self, *, current_user: models.User) -> List[models.Conversation]:
        return (
            self.db.query(models.Conversation)
            .join(models.ConversationMember)
            .filter(
                models.ConversationMember.user_id == current_user.id,
                models.Conversation.is_active.is_(True),
            )
            .options(joinedload(models.Conversation.members))
            .order_by(models.Conversation.last_message_at.desc().nullslast())
            .all()
        )

    def add_members_to_conversation(
        self,
        *,
        conversation_id: str,
        member_ids: List[int],
        current_user: models.User,
    ) -> models.Conversation:
        conversation = self._get_conversation_or_404(conversation_id)
        self._ensure_conversation_manager(conversation_id, current_user.id)
        for uid in member_ids:
            exists = (
                self.db.query(models.ConversationMember)
                .filter(
                    models.ConversationMember.conversation_id == conversation_id,
                    models.ConversationMember.user_id == uid,
                )
                .first()
            )
            if not exists:
                self.db.add(
                    models.ConversationMember(
                        conversation_id=conversation_id,
                        user_id=uid,
                        role=models.ConversationMemberRole.MEMBER,
                    )
                )
        self.db.commit()
        self.db.refresh(conversation)
        return conversation

    def remove_member_from_conversation(
        self,
        *,
        conversation_id: str,
        user_id: int,
        current_user: models.User,
    ) -> models.Conversation:
        conversation = self._get_conversation_or_404(conversation_id)
        self._ensure_conversation_manager(conversation_id, current_user.id)
        member = (
            self.db.query(models.ConversationMember)
            .filter(
                models.ConversationMember.conversation_id == conversation_id,
                models.ConversationMember.user_id == user_id,
            )
            .first()
        )
        if not member:
            raise HTTPException(status_code=404, detail="Member not found in conversation")
        if member.role == models.ConversationMemberRole.OWNER:
            raise HTTPException(status_code=400, detail="Cannot remove the conversation owner")
        self.db.delete(member)
        self.db.commit()
        self.db.refresh(conversation)
        return conversation

    def get_conversation_messages(
        self,
        *,
        conversation_id: str,
        current_user: models.User,
        skip: int,
        limit: int,
    ) -> List[models.Message]:
        self._ensure_conversation_membership(conversation_id, current_user.id)
        return (
            self.db.query(models.Message)
            .filter(models.Message.conversation_id == conversation_id)
            .order_by(models.Message.timestamp.desc())
            .offset(skip)
            .limit(limit)
            .all()
        )

    async def get_inbox(
        self, *, current_user: models.User, skip: int, limit: int
    ) -> List[schemas.MessageOut]:
        messages = (
            self.db.query(models.Message)
            .filter(models.Message.receiver_id == current_user.id)
            .order_by(models.Message.timestamp.desc())
            .offset(skip)
            .limit(limit)
            .all()
        )
        return [schemas.MessageOut(message=message, count=1) for message in messages]

    async def search_messages(
        self,
        *,
        params: schemas.MessageSearch,
        current_user: models.User,
        skip: int,
        limit: int,
    ) -> schemas.MessageSearchResponse:
        message_query = self.db.query(models.Message).filter(
            or_(
                models.Message.sender_id == current_user.id,
                models.Message.receiver_id == current_user.id,
            )
        )
        if params.query:
            message_query = message_query.filter(
                models.Message.content.ilike(f"%{params.query}%")
            )
        if params.start_date:
            message_query = message_query.filter(
                models.Message.timestamp >= params.start_date
            )
        if params.end_date:
            message_query = message_query.filter(
                models.Message.timestamp <= params.end_date
            )
        if params.message_type:
            message_query = message_query.filter(
                models.Message.message_type == params.message_type
            )
        if params.conversation_id:
            message_query = message_query.filter(
                models.Message.conversation_id == params.conversation_id
            )

        total = message_query.count()
        if params.sort_order == schemas.SortOrder.ASC:
            message_query = message_query.order_by(models.Message.timestamp.asc())
        else:
            message_query = message_query.order_by(models.Message.timestamp.desc())

        messages = message_query.offset(skip).limit(limit).all()
        return schemas.MessageSearchResponse(total=total, messages=messages)

    async def get_message(
        self, *, message_id: int, current_user: models.User
    ) -> models.Message:
        message = (
            self.db.query(models.Message).filter(models.Message.id == message_id).first()
        )
        if not message:
            raise HTTPException(status_code=404, detail="Message not found")
        if message.sender_id != current_user.id and message.receiver_id != current_user.id:
            raise HTTPException(status_code=403, detail="Not authorized to view this message")
        return message

    async def update_read_status_visibility(
        self, *, user_update: schemas.UserUpdate, current_user: models.User
    ) -> models.User:
        if user_update.hide_read_status is not None:
            current_user.hide_read_status = user_update.hide_read_status
            self.db.commit()
            self.db.refresh(current_user)
        return current_user


__all__ = ["MessageService"]
