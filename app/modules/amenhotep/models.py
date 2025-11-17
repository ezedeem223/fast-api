"""Amenhotep AI chat models and helpers."""

from __future__ import annotations

from sqlalchemy import (
    Column,
    Integer,
    String,
    DateTime,
    Float,
    ForeignKey,
    Text,
)
from sqlalchemy.types import TypeDecorator, JSON
from sqlalchemy.dialects.postgresql import ARRAY as PG_ARRAY
from app.core.config import settings
from app.core.database import Base
from app.core.db_defaults import timestamp_default
from sqlalchemy.orm import relationship


DATABASE_URL = settings.get_database_url(
    use_test=settings.environment.lower() == "test"
)
IS_POSTGRES = DATABASE_URL.startswith("postgresql")

if IS_POSTGRES:
    ARRAY = PG_ARRAY
else:

    class SqliteArray(TypeDecorator):
        """SQLite-friendly ARRAY replacement."""

        impl = JSON
        cache_ok = True

        def process_bind_param(self, value, dialect):
            if value is None:
                return []
            if isinstance(value, list):
                return value
            return list(value)

        def process_result_value(self, value, dialect):
            if value is None:
                return []
            return value

    ARRAY = SqliteArray


class AmenhotepMessage(Base):
    """Persisted Amenhotep chat exchange."""

    __tablename__ = "amenhotep_messages"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"))
    message = Column(String, nullable=False)
    response = Column(String, nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=timestamp_default())

    user = relationship("User", back_populates="amenhotep_messages")


class AmenhotepChatAnalytics(Base):
    """Aggregated analytics for Amenhotep chat sessions."""

    __tablename__ = "amenhotep_chat_analytics"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"))
    session_id = Column(String, index=True)
    total_messages = Column(Integer, default=0)
    topics_discussed = Column(ARRAY(String), default=list)
    session_duration = Column(Integer)
    satisfaction_score = Column(Float, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=timestamp_default())

    user = relationship("User", back_populates="amenhotep_analytics")


class CommentEditHistory(Base):
    """Track edits performed on comments."""

    __tablename__ = "comment_edit_history"

    id = Column(Integer, primary_key=True, nullable=False)
    comment_id = Column(
        Integer,
        ForeignKey(
            "comments.id",
            use_alter=True,
            name="fk_comment_edit_history_comment_id",
            ondelete="CASCADE",
        ),
        nullable=False,
    )
    previous_content = Column(Text, nullable=False)
    edited_at = Column(
        DateTime(timezone=True), nullable=False, server_default=timestamp_default()
    )

    comment = relationship("Comment", back_populates="edit_history")


__all__ = ["AmenhotepMessage", "AmenhotepChatAnalytics", "CommentEditHistory"]
