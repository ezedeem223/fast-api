"""Application services for the users domain."""

from __future__ import annotations

from typing import Tuple, List

from fastapi import HTTPException, status, UploadFile
from sqlalchemy import desc, asc
from sqlalchemy.orm import Session
from pathlib import Path

from app import models, schemas, utils
from .models import User
from app.i18n import ALL_LANGUAGES


class UserService:
    """Encapsulates user-centric business logic shared across routers."""

    def __init__(self, db: Session):
        self.db = db

    def create_user(self, payload: schemas.UserCreate) -> User:
        """Create a new user after validating uniqueness."""
        existing_user = self.db.query(User).filter(User.email == payload.email).first()
        if existing_user:
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

    def get_user_followers(
        self,
        user_id: int,
        requesting_user: User,
        sort_by: schemas.SortOption,
        order: str,
        skip: int,
        limit: int,
    ) -> Tuple[User, List[models.Follow], int]:
        """Return followers for a user along with total count after privacy checks."""
        user = self.db.query(User).filter(User.id == user_id).first()
        if not user:
            raise HTTPException(status_code=404, detail="User not found")

        self._ensure_followers_visibility(user, requesting_user)

        query = (
            self.db.query(models.Follow)
            .join(User, User.id == models.Follow.follower_id)
            .filter(models.Follow.followed_id == user_id)
        )

        order_column = self._resolve_followers_sort_column(sort_by)
        if order == "desc":
            query = query.order_by(desc(order_column))
        else:
            query = query.order_by(asc(order_column))

        total_count = query.count()
        followers = query.offset(skip).limit(limit).all()
        return user, followers, total_count

    def _resolve_followers_sort_column(self, sort_by: schemas.SortOption):
        mapping = {
            schemas.SortOption.DATE: models.Follow.created_at,
            schemas.SortOption.USERNAME: User.username,
            schemas.SortOption.POST_COUNT: User.post_count,
            schemas.SortOption.INTERACTION_COUNT: User.interaction_count,
        }
        return mapping.get(sort_by, models.Follow.created_at)

    def _ensure_followers_visibility(self, target: User, requester: User) -> None:
        """Raise an HTTP error if the requester cannot view the target's followers."""
        if target.followers_visibility == "private" and target.id != requester.id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Followers list is private",
            )

        if target.followers_visibility == "custom" and target.id != requester.id:
            allowed_users = (target.followers_custom_visibility or {}).get(
                "allowed_users", []
            )
            if requester.id not in allowed_users:
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="You don't have permission to view this followers list",
                )

    def update_followers_settings(
        self, current_user: User, settings: schemas.UserFollowersSettings
    ) -> schemas.UserFollowersSettings:
        """Persist follower visibility preferences for the current user."""
        current_user.followers_visibility = settings.followers_visibility
        current_user.followers_custom_visibility = (
            settings.followers_custom_visibility or {}
        )
        current_user.followers_sort_preference = (
            settings.followers_sort_preference or current_user.followers_sort_preference
        )
        self.db.commit()
        return settings

    def get_user_or_404(self, user_id: int) -> User:
        user = self.db.query(User).filter(User.id == user_id).first()
        if not user:
            raise HTTPException(status_code=404, detail="User not found")
        return user

    def update_public_key(
        self, current_user: User, update: schemas.UserPublicKeyUpdate
    ) -> User:
        """Update and persist the user's public key."""
        current_user.public_key = update.public_key
        self.db.commit()
        self.db.refresh(current_user)
        return current_user

    def update_language_preferences(
        self, current_user: User, language: schemas.UserLanguageUpdate
    ) -> dict:
        """Validate and persist language / auto-translate preferences."""
        if language.preferred_language not in ALL_LANGUAGES:
            raise HTTPException(status_code=400, detail="Invalid language code")

        current_user.preferred_language = language.preferred_language
        current_user.auto_translate = language.auto_translate
        self.db.commit()
        return {"message": "Language preferences updated successfully"}

    def verify_user_document(self, current_user: User, file: UploadFile) -> str:
        """Validate and store the verification document, updating the user record."""
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
