"""Association tables shared across user-related models."""

from sqlalchemy import Column, ForeignKey, Integer, Table

from app.core.database import Base


post_mentions = Table(
    "post_mentions",
    Base.metadata,
    Column("post_id", Integer, ForeignKey("posts.id", ondelete="CASCADE")),
    Column("user_id", Integer, ForeignKey("users.id", ondelete="CASCADE")),
)

user_hashtag_follows = Table(
    "user_hashtag_follows",
    Base.metadata,
    Column("user_id", Integer, ForeignKey("users.id", ondelete="CASCADE")),
    Column("hashtag_id", Integer, ForeignKey("hashtags.id", ondelete="CASCADE")),
)

__all__ = ["post_mentions", "user_hashtag_follows"]

