from sqlalchemy import Column, Integer, String, Boolean, ForeignKey, Index
from sqlalchemy.sql.expression import text
from sqlalchemy.sql.sqltypes import TIMESTAMP
from .database import Base
from sqlalchemy.orm import relationship


class Post(Base):
    __tablename__ = "posts"

    id = Column(Integer, primary_key=True, nullable=False)
    title = Column(String, nullable=False)
    content = Column(String, nullable=False)
    published = Column(Boolean, server_default="True", nullable=False)
    created_at = Column(
        TIMESTAMP(timezone=True), nullable=False, server_default=text("now()")
    )
    user_id = Column(Integer, ForeignKey("users.id"))
    owner_id = Column(
        Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )

    __table_args__ = (Index("idx_title_user", "title", "user_id"),)

    # Define relationships with explicit join conditions
    owner = relationship(
        "User", primaryjoin="Post.owner_id == User.id", back_populates="posts"
    )
    comments = relationship(
        "Comment", primaryjoin="Post.id == Comment.post_id", back_populates="post"
    )
    reports = relationship(
        "Report", primaryjoin="Post.id == Report.post_id", back_populates="post"
    )

    is_safe_content = Column(Boolean, default=True)
    is_short_video = Column(Boolean, default=False)


class Comment(Base):
    __tablename__ = "comments"

    id = Column(Integer, primary_key=True, nullable=False)
    content = Column(String, nullable=False)
    post_id = Column(
        Integer, ForeignKey("posts.id", ondelete="CASCADE"), nullable=False
    )
    owner_id = Column(
        Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    created_at = Column(
        TIMESTAMP(timezone=True), nullable=False, server_default=text("now()")
    )

    # Define relationships with explicit join conditions
    owner = relationship(
        "User", primaryjoin="Comment.owner_id == User.id", back_populates="comments"
    )
    post = relationship(
        "Post", primaryjoin="Comment.post_id == Post.id", back_populates="comments"
    )

    # Add relationship to Report model
    reports = relationship(
        "Report",
        primaryjoin="Comment.id == Report.comment_id",
        back_populates="comment",
    )


class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, nullable=False)
    email = Column(String, nullable=False, unique=True)
    password = Column(String, nullable=False)
    created_at = Column(
        TIMESTAMP(timezone=True), nullable=False, server_default=text("now()")
    )
    phone_number = Column(String)

    # New fields for verification
    is_verified = Column(Boolean, default=False)
    verification_document = Column(String, nullable=True)
    otp_secret = Column(String, nullable=True)

    # Relationships
    posts = relationship(
        "Post", primaryjoin="User.id == Post.owner_id", back_populates="owner"
    )
    comments = relationship(
        "Comment", primaryjoin="User.id == Comment.owner_id", back_populates="owner"
    )
    reports = relationship(
        "Report", primaryjoin="User.id == Report.reporter_id", back_populates="reporter"
    )
    follows = relationship(
        "Follow", primaryjoin="User.id == Follow.follower_id", back_populates="follower"
    )
    followed_by = relationship(
        "Follow", primaryjoin="User.id == Follow.followed_id", back_populates="followed"
    )
    sent_messages = relationship(
        "Message", primaryjoin="User.id == Message.sender_id", back_populates="sender"
    )
    received_messages = relationship(
        "Message",
        primaryjoin="User.id == Message.receiver_id",
        back_populates="receiver",
    )
    communities = relationship(
        "Community", primaryjoin="User.id == Community.owner_id", back_populates="owner"
    )
    blocks = relationship(
        "Block", primaryjoin="User.id == Block.follower_id", back_populates="follower"
    )
    blocked_by = relationship(
        "Block", primaryjoin="User.id == Block.blocked_id", back_populates="blocked"
    )


class Vote(Base):
    __tablename__ = "votes"
    user_id = Column(
        Integer, ForeignKey("users.id", ondelete="CASCADE"), primary_key=True
    )
    post_id = Column(
        Integer, ForeignKey("posts.id", ondelete="CASCADE"), primary_key=True
    )


class Report(Base):
    __tablename__ = "reports"

    id = Column(Integer, primary_key=True, nullable=False)
    report_reason = Column(String, nullable=False)
    post_id = Column(Integer, ForeignKey("posts.id", ondelete="CASCADE"), nullable=True)
    comment_id = Column(
        Integer, ForeignKey("comments.id", ondelete="CASCADE"), nullable=True
    )
    reporter_id = Column(
        Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    created_at = Column(
        TIMESTAMP(timezone=True), nullable=False, server_default=text("now()")
    )

    # Define relationships with explicit join conditions
    reporter = relationship(
        "User", primaryjoin="Report.reporter_id == User.id", back_populates="reports"
    )
    post = relationship(
        "Post", primaryjoin="Report.post_id == Post.id", back_populates="reports"
    )
    comment = relationship(
        "Comment",
        primaryjoin="Report.comment_id == Comment.id",
        back_populates="reports",
    )


class Follow(Base):
    __tablename__ = "follows"
    follower_id = Column(
        Integer, ForeignKey("users.id", ondelete="CASCADE"), primary_key=True
    )
    followed_id = Column(
        Integer, ForeignKey("users.id", ondelete="CASCADE"), primary_key=True
    )
    created_at = Column(
        TIMESTAMP(timezone=True), nullable=False, server_default=text("now()")
    )

    # Define relationships with explicit join conditions
    follower = relationship(
        "User", primaryjoin="Follow.follower_id == User.id", back_populates="follows"
    )
    followed = relationship(
        "User",
        primaryjoin="Follow.followed_id == User.id",
        back_populates="followed_by",
    )


class Message(Base):
    __tablename__ = "messages"
    id = Column(Integer, primary_key=True, index=True)
    sender_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"))
    receiver_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"))
    content = Column(String, nullable=False)
    timestamp = Column(
        TIMESTAMP(timezone=True), nullable=False, server_default=text("now()")
    )

    # Define relationships with explicit join conditions
    sender = relationship(
        "User",
        primaryjoin="Message.sender_id == User.id",
        back_populates="sent_messages",
    )
    receiver = relationship(
        "User",
        primaryjoin="Message.receiver_id == User.id",
        back_populates="received_messages",
    )


class Community(Base):
    __tablename__ = "communities"
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, nullable=False, unique=True)
    description = Column(String)
    created_at = Column(
        TIMESTAMP(timezone=True), nullable=False, server_default=text("now()")
    )
    owner_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"))

    # Define relationship with explicit join condition
    owner = relationship(
        "User",
        primaryjoin="Community.owner_id == User.id",
        back_populates="communities",
    )


class Block(Base):
    __tablename__ = "blocks"
    follower_id = Column(
        Integer, ForeignKey("users.id", ondelete="CASCADE"), primary_key=True
    )
    blocked_id = Column(
        Integer, ForeignKey("users.id", ondelete="CASCADE"), primary_key=True
    )
    created_at = Column(
        TIMESTAMP(timezone=True), nullable=False, server_default=text("now()")
    )

    # Define relationships with explicit join conditions
    follower = relationship(
        "User", primaryjoin="Block.follower_id == User.id", back_populates="blocks"
    )
    blocked = relationship(
        "User", primaryjoin="Block.blocked_id == User.id", back_populates="blocked_by"
    )
