"""Association tables for the community domain."""

from sqlalchemy import Column, ForeignKey, Integer, Table

from app.core.database import Base

community_tags = Table(
    "community_tags",
    Base.metadata,
    Column(
        "community_id",
        Integer,
        ForeignKey("communities.id", ondelete="CASCADE"),
    ),
    Column(
        "tag_id",
        Integer,
        ForeignKey("tags.id", ondelete="CASCADE"),
    ),
)

__all__ = ["community_tags"]
