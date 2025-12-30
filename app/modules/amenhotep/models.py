"""Amenhotep AI chat models and helpers."""

from __future__ import annotations

from sqlalchemy import JSON, Column, DateTime, Float, ForeignKey, Integer, String, Text
from sqlalchemy.dialects.postgresql import ARRAY as PG_ARRAY
from sqlalchemy.orm import relationship

from app.core.database import Base
from app.core.db_defaults import timestamp_default


def _array_type(item_type):
    """
    Return an ARRAY that transparently stores JSON when using SQLite.
    """
    base = PG_ARRAY(item_type)
    return base.with_variant(JSON, "sqlite").with_variant(JSON, "sqlite+pysqlite")


class AmenhotepMessage(Base):
    """Persisted Amenhotep chat exchange (user prompt and model response)."""

    __tablename__ = "amenhotep_messages"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"))
    message = Column(String, nullable=False)
    response = Column(String, nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=timestamp_default())

    user = relationship("User", back_populates="amenhotep_messages")


class AmenhotepChatAnalytics(Base):
    """Aggregated analytics for Amenhotep chat sessions (topics, duration, satisfaction)."""

    __tablename__ = "amenhotep_chat_analytics"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"))
    session_id = Column(String, index=True)
    total_messages = Column(Integer, default=0)
    topics_discussed = Column(_array_type(String), default=list)
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
