"""High-level business services for the users domain."""

from __future__ import annotations

from pathlib import Path
from typing import List, Tuple

from fastapi import HTTPException, status, UploadFile
from sqlalchemy import asc, desc, or_
from sqlalchemy.orm import Session, joinedload

from app import models, schemas, utils, notifications
from app.modules.users.models import User
from app.i18n import ALL_LANGUAGES


class UserService:
    """Encapsulates shared user operations used by routers and background tasks."""

    def __init__(self, db: Session):
        self.db = db

    # ----- Creation & profile -----
    def create_user(self, payload: schemas.UserCreate) -> User:
        existing = self.db.query(User).filter(User.email == payload.email).first()
        if existing:
            raise HTTPException(status_code=400, detail="Email already registered")
        hashed_password = utils.hash(payload.password)
        new_user = User(
            email=payload.email,
            hashed_password=hashed_password,
            public_key=payload.public_key,
            **payload.model_dump(exclude={"password", "public_key", "email"}),
        )
        self.db.add(new_user)
        self.db.commit()
        self.db.refresh(new_user)
        return new_user

    def update_profile(
        self, current_user: User, profile_update: schemas.UserProfileUpdate
    ) -> schemas.UserProfileOut:
        for key, value in profile_update.model_dump(exclude_unset=True).items():
            setattr(current_user, key, value)
        self.db.commit()
        self.db.refresh(current_user)
        return schemas.UserProfileOut.from_orm(current_user)

    def update_public_key(
        self, current_user: User, update: schemas.UserPublicKeyUpdate
    ) -> User:
        current_user.public_key = update.public_key
        self.db.commit()
        self.db.refresh(current_user)
        return current_user

    def update_language_preferences(
        self, current_user: User, language: schemas.UserLanguageUpdate
    ) -> dict:
        if language.preferred_language not in ALL_LANGUAGES:
            raise HTTPException(status_code=400, detail="Invalid language code")
        current_user.preferred_language = language.preferred_language
        current_user.auto_translate = language.auto_translate
        self.db.commit()
        return {"message": "Language preferences updated successfully"}

    # ----- Access helpers -----
    def get_user_or_404(self, user_id: int) -> User:
        user = self.db.query(User).filter(User.id == user_id).first()
        if not user:
            raise HTTPException(status_code=404, detail="User not found")
        return user

    # ----- Followers -----
    def get_user_followers(
        self,
        user_id: int,
        requesting_user: User,
        sort_by: schemas.SortOption,
        order: str,
        skip: int,
        limit: int,
    ) -> Tuple[User, List[models.Follow], int]:
        user = self.get_user_or_404(user_id)
        self._ensure_followers_visibility(user, requesting_user)
        query = (
            self.db.query(models.Follow)
            .join(User, User.id == models.Follow.follower_id)
            .filter(models.Follow.followed_id == user_id)
        )
        order_column = self._resolve_followers_sort_column(sort_by)
        query = query.order_by(desc(order_column) if order == "desc" else asc(order_column))
        total = query.count()
        followers = query.offset(skip).limit(limit).all()
        return user, followers, total

    def _ensure_followers_visibility(self, target: User, requester: User) -> None:
        if target.followers_visibility == "private" and target.id != requester.id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Followers list is private",
            )
        if target.followers_visibility == "custom" and target.id != requester.id:
            allowed = (target.followers_custom_visibility or {}).get(
                "allowed_users", []
            )
            if requester.id not in allowed:
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="You don't have permission to view this followers list",
                )

    def _resolve_followers_sort_column(self, sort_by: schemas.SortOption):
        mapping = {
            schemas.SortOption.DATE: models.Follow.created_at,
            schemas.SortOption.USERNAME: User.username,
            schemas.SortOption.POST_COUNT: User.post_count,
            schemas.SortOption.INTERACTION_COUNT: User.interaction_count,
        }
        return mapping.get(sort_by, models.Follow.created_at)

    def update_followers_settings(
        self, current_user: User, settings: schemas.UserFollowersSettings
    ) -> schemas.UserFollowersSettings:
        current_user.followers_visibility = settings.followers_visibility
        current_user.followers_custom_visibility = (
            settings.followers_custom_visibility or {}
        )
        current_user.followers_sort_preference = (
            settings.followers_sort_preference or current_user.followers_sort_preference
        )
        self.db.commit()
        return settings

    # ----- Verification -----
    def verify_user_document(self, current_user: User, file: UploadFile) -> str:
        if file.content_type not in {"image/jpeg", "image/png", "application/pdf"}:
            raise HTTPException(status_code=400, detail="Unsupported file type.")
        file_location = Path("static") / file.filename
        file_location.parent.mkdir(parents=True, exist_ok=True)
        with file_location.open("wb+") as buffer:
            buffer.write(file.file.read())
        current_user.verification_document = str(file_location)
        current_user.is_verified = True
        self.db.commit()
        return str(file_location)

    # ----- Content aggregation -----
    def get_user_content(
        self, current_user: User, skip: int, limit: int
    ) -> schemas.UserContentOut:
        posts_query = self.db.query(models.Post).filter(
            models.Post.owner_id == current_user.id
        )
        if current_user.privacy_level == models.PrivacyLevel.CUSTOM:
            allowed = current_user.custom_privacy.get("allowed_users", [])
            posts_query = posts_query.filter(
                or_(
                    models.Post.privacy_level == models.PrivacyLevel.PUBLIC,
                    models.Post.id.in_(allowed),
                )
            )
        elif current_user.privacy_level == models.PrivacyLevel.PUBLIC:
            posts_query = posts_query.filter(
                models.Post.privacy_level == models.PrivacyLevel.PUBLIC
            )

        posts = (
            posts_query.options(joinedload(models.Post.owner))
            .order_by(models.Post.created_at.desc())
            .offset(skip)
            .limit(limit)
            .all()
        )

        comments = (
            self.db.query(models.Comment)
            .filter(models.Comment.owner_id == current_user.id)
            .options(joinedload(models.Comment.post))
            .order_by(models.Comment.created_at.desc())
            .offset(skip)
            .limit(limit)
            .all()
        )
        articles = (
            self.db.query(models.Article)
            .filter(models.Article.author_id == current_user.id)
            .options(joinedload(models.Article.author))
            .order_by(models.Article.created_at.desc())
            .offset(skip)
            .limit(limit)
            .all()
        )
        reels = (
            self.db.query(models.Reel)
            .filter(models.Reel.owner_id == current_user.id)
            .options(joinedload(models.Reel.owner))
            .order_by(models.Reel.created_at.desc())
            .offset(skip)
            .limit(limit)
            .all()
        )

        return schemas.UserContentOut(
            posts=[schemas.PostOut.from_orm(post) for post in posts],
            comments=[schemas.Comment.from_orm(comment) for comment in comments],
            articles=[schemas.ArticleOut.from_orm(article) for article in articles],
            reels=[schemas.ReelOut.from_orm(reel) for reel in reels],
        )

    # ----- Notifications -----
    def get_user_notifications(
        self, current_user: User, skip: int, limit: int
    ) -> list[models.Notification]:
        return (
            self.db.query(models.Notification)
            .filter(models.Notification.user_id == current_user.id)
            .order_by(models.Notification.created_at.desc())
            .offset(skip)
            .limit(limit)
            .all()
        )

    def mark_notification_as_read(
        self, notification_id: int, current_user: User
    ) -> models.Notification:
        notification = (
            self.db.query(models.Notification)
            .filter(
                models.Notification.id == notification_id,
                models.Notification.user_id == current_user.id,
            )
            .first()
        )
        if not notification:
            raise HTTPException(status_code=404, detail="Notification not found")
        notification.is_read = True
        self.db.commit()
        self.db.refresh(notification)
        return notification

    # ----- Suspension -----
    def suspend_user(self, user_id: int, days: int) -> dict:
        user = self.get_user_or_404(user_id)
        user.is_suspended = True
        user.suspension_end_date = utils.utcnow() + timedelta(days=days)
        self.db.commit()
        return {"message": "User suspended successfully"}

    def unsuspend_user(self, user_id: int) -> dict:
        user = self.get_user_or_404(user_id)
        user.is_suspended = False
        user.suspension_end_date = None
        self.db.commit()
        return {"message": "User unsuspended successfully"}

    # Utility logging hook
    def log_activity(self, user_id: int, activity_type: str, details: dict) -> None:
        activity = models.UserActivity(
            user_id=user_id, activity_type=activity_type, details=details
        )
        self.db.add(activity)
        self.db.commit()
