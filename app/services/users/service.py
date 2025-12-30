"""High-level business services for the users domain."""

from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Dict, List, Tuple

import pyotp
from sqlalchemy import asc, desc, func, or_
from sqlalchemy.orm import Session, joinedload

from app import models, schemas
from app.i18n import ALL_LANGUAGES
from app.modules.users.models import (
    TokenBlacklist,
    User,
    UserActivity,
    UserIdentity,
    UserSession,
    UserStatistics,
)
from app.modules.utils.security import hash as hash_password
from app.modules.utils.security import verify
from fastapi import HTTPException, UploadFile, status


class UserService:
    """Encapsulates shared user operations used by routers and background tasks."""

    def __init__(self, db: Session):
        self.db = db

    # ----- Creation & profile -----
    def create_user(self, payload: schemas.UserCreate) -> User:
        existing = self.db.query(User).filter(User.email == payload.email).first()
        if existing:
            raise HTTPException(status_code=400, detail="Email already registered")

        hashed_password = hash_password(payload.password)
        coerced_public_key = self._coerce_public_key(payload.public_key)
        new_user = User(
            email=payload.email,
            hashed_password=hashed_password,
            public_key=coerced_public_key,
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

    def update_privacy_settings(
        self, current_user: User, privacy_settings: schemas.UserPrivacyUpdate
    ) -> User:
        if (
            privacy_settings.privacy_level == schemas.PrivacyLevel.CUSTOM
            and not privacy_settings.custom_privacy
        ):
            raise HTTPException(
                status_code=400,
                detail="Custom privacy settings required for CUSTOM privacy level",
            )

        current_user.privacy_level = privacy_settings.privacy_level
        if privacy_settings.custom_privacy:
            current_user.custom_privacy = privacy_settings.custom_privacy

        self.db.commit()
        self.db.refresh(current_user)
        return current_user

    def update_public_key(
        self, current_user: User, update: schemas.UserPublicKeyUpdate
    ) -> User:
        current_user.public_key = self._coerce_public_key(update.public_key)
        self.db.commit()
        self.db.refresh(current_user)
        return current_user

    def _coerce_public_key(self, value):
        if value is None:
            return None
        if isinstance(value, (bytes, bytearray, memoryview)):
            return bytes(value)
        if isinstance(value, str):
            return value.encode()
        raise HTTPException(
            status_code=400, detail="Invalid public key type; expected bytes or str"
        )

    def update_language_preferences(
        self, current_user: User, language: schemas.UserLanguageUpdate
    ) -> Dict[str, str]:
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
        query = query.order_by(
            desc(order_column) if order == "desc" else asc(order_column)
        )

        total = query.count()
        followers = query.offset(skip).limit(limit).all()
        return user, followers, total

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

    # ----- Verification & media -----
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

    def upload_profile_image(self, current_user: User, file: UploadFile) -> str:
        if file.content_type not in {"image/jpeg", "image/png"}:
            raise HTTPException(
                status_code=400,
                detail="Unsupported file type. Only JPEG and PNG are allowed.",
            )

        directory = Path("static/profile_images")
        directory.mkdir(parents=True, exist_ok=True)
        file_location = directory / f"{current_user.id}_{file.filename}"

        with file_location.open("wb+") as file_object:
            file_object.write(file.file.read())

        current_user.profile_image = str(file_location)
        self.db.commit()
        self.db.refresh(current_user)
        return current_user.profile_image

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
        now = datetime.now(timezone.utc)
        reels = (
            self.db.query(models.Reel)
            .filter(
                models.Reel.owner_id == current_user.id,
                models.Reel.is_active.is_(True),
                models.Reel.expires_at > now,
            )
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

    def get_user_posts(
        self, user_id: int, skip: int, limit: int
    ) -> List[schemas.PostOut]:
        posts = (
            self.db.query(models.Post)
            .filter(models.Post.owner_id == user_id)
            .offset(skip)
            .limit(limit)
            .all()
        )
        return [schemas.PostOut.from_orm(post) for post in posts]

    def get_user_articles(
        self, user_id: int, skip: int, limit: int
    ) -> List[schemas.ArticleOut]:
        articles = (
            self.db.query(models.Article)
            .filter(models.Article.author_id == user_id)
            .offset(skip)
            .limit(limit)
            .all()
        )
        return [schemas.ArticleOut.from_orm(article) for article in articles]

    def get_user_media(
        self, user_id: int, skip: int, limit: int
    ) -> List[schemas.PostOut]:
        media = (
            self.db.query(models.Post)
            .filter(
                models.Post.owner_id == user_id,
                or_(
                    models.Post.content.like("%image%"),
                    models.Post.content.like("%video%"),
                ),
            )
            .offset(skip)
            .limit(limit)
            .all()
        )
        return [schemas.PostOut.from_orm(item) for item in media]

    def get_user_likes(
        self, user_id: int, skip: int, limit: int
    ) -> List[schemas.PostOut]:
        liked_posts = (
            self.db.query(models.Post)
            .join(models.Vote)
            .filter(models.Vote.user_id == user_id)
            .offset(skip)
            .limit(limit)
            .all()
        )
        return [schemas.PostOut.from_orm(post) for post in liked_posts]

    def get_profile_overview(self, user_id: int) -> Tuple[User, Dict[str, int]]:
        user = self.get_user_or_404(user_id)
        metrics = {
            "post_count": (
                self.db.query(func.count(models.Post.id))
                .filter(models.Post.owner_id == user_id)
                .scalar()
                or 0
            ),
            "follower_count": (
                self.db.query(func.count(models.Follow.follower_id))
                .filter(models.Follow.followed_id == user_id)
                .scalar()
                or 0
            ),
            "following_count": (
                self.db.query(func.count(models.Follow.followed_id))
                .filter(models.Follow.follower_id == user_id)
                .scalar()
                or 0
            ),
            "community_count": (
                self.db.query(func.count(models.CommunityMember.user_id))
                .filter(models.CommunityMember.user_id == user_id)
                .scalar()
                or 0
            ),
            "media_count": (
                self.db.query(func.count(models.Post.id))
                .filter(
                    models.Post.owner_id == user_id,
                    or_(
                        models.Post.content.like("%image%"),
                        models.Post.content.like("%video%"),
                    ),
                )
                .scalar()
                or 0
            ),
        }
        return user, metrics

    # ----- Notifications -----
    def get_user_notifications(
        self, current_user: User, skip: int, limit: int
    ) -> List[models.Notification]:
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

    # ----- Security & sessions -----
    def change_password(
        self, current_user: User, password_change: schemas.PasswordChange
    ) -> Dict[str, str]:
        if not verify(password_change.current_password, current_user.hashed_password):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST, detail="Incorrect password"
            )

        current_user.hashed_password = hash_password(password_change.new_password)
        self.db.commit()
        return {"message": "Password changed successfully"}

    def enable_2fa(self, current_user: User) -> Dict[str, str]:
        if current_user.otp_secret:
            raise HTTPException(status_code=400, detail="2FA is already enabled")

        secret = pyotp.random_base32()
        current_user.otp_secret = secret
        current_user.is_2fa_enabled = False
        self.db.commit()
        return {"otp_secret": secret}

    def verify_2fa(self, current_user: User, otp: str) -> Dict[str, str]:
        if not current_user.otp_secret:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="2FA is not enabled for this user.",
            )

        totp = pyotp.TOTP(current_user.otp_secret)
        if not totp.verify(otp):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid OTP"
            )

        current_user.is_2fa_enabled = True
        self.db.commit()
        return {"message": "2FA verified successfully"}

    def disable_2fa(self, current_user: User) -> Dict[str, str]:
        if not current_user.otp_secret:
            raise HTTPException(status_code=400, detail="2FA is not enabled")

        current_user.otp_secret = None
        current_user.is_2fa_enabled = False
        self.db.commit()
        return {"message": "2FA disabled successfully"}

    def logout_other_sessions(
        self, current_user: User, current_session: str
    ) -> Dict[str, str]:
        (
            self.db.query(UserSession)
            .filter(
                UserSession.user_id == current_user.id,
                UserSession.session_id != current_session,
            )
            .delete(synchronize_session=False)
        )
        self.db.commit()
        return {"message": "Logged out from all other devices"}

    def list_sessions(self, current_user: User) -> List[UserSession]:
        """Return active sessions for the current user."""
        return (
            self.db.query(UserSession)
            .filter(UserSession.user_id == current_user.id)
            .order_by(UserSession.created_at.desc())
            .all()
        )

    def revoke_session(self, current_user: User, session_id: str) -> Dict[str, str]:
        """Terminate a specific session for the current user."""
        session_obj = (
            self.db.query(UserSession)
            .filter(
                UserSession.user_id == current_user.id,
                UserSession.session_id == session_id,
            )
            .first()
        )
        if not session_obj:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Session not found",
            )
        self.db.delete(session_obj)
        self.db.commit()
        # Optionally blacklist the session id to prevent reuse.
        token_entry = TokenBlacklist(token=session_id, user_id=current_user.id)
        self.db.add(token_entry)
        self.db.commit()
        return {"message": "Session revoked"}

    # ----- Discovery -----
    def get_suggested_follows(self, current_user: User, limit: int) -> List[User]:
        if not current_user.interests:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="User has no interests set",
            )

        similar_interests = (
            self.db.query(User.id)
            .filter(User.id != current_user.id)
            .filter(User.interests.overlap(current_user.interests))
            .subquery()
        )

        followed_by_current_user = (
            self.db.query(models.Follow.followed_id)
            .filter(models.Follow.follower_id == current_user.id)
            .subquery()
        )

        followers_of_followed = (
            self.db.query(models.Follow.follower_id)
            .filter(models.Follow.followed_id.in_(followed_by_current_user))
            .subquery()
        )

        suggested_users = (
            self.db.query(User)
            .outerjoin(similar_interests, User.id == similar_interests.c.id)
            .outerjoin(
                followers_of_followed, User.id == followers_of_followed.c.follower_id
            )
            .filter(User.id != current_user.id)
            .filter(~User.id.in_(followed_by_current_user))
            .group_by(User.id)
            .order_by(
                func.count(similar_interests.c.id).desc(),
                func.count(followers_of_followed.c.follower_id).desc(),
            )
            .limit(limit)
            .all()
        )

        return suggested_users

    # ----- Analytics -----
    def get_user_analytics(
        self, current_user: User, days: int
    ) -> schemas.UserAnalytics:
        end_date = date.today()
        start_date = end_date - timedelta(days=days)

        daily_stats = (
            self.db.query(UserStatistics)
            .filter(
                UserStatistics.user_id == current_user.id,
                UserStatistics.date.between(start_date, end_date),
            )
            .all()
        )

        totals = (
            self.db.query(
                func.sum(UserStatistics.post_count).label("total_posts"),
                func.sum(UserStatistics.comment_count).label("total_comments"),
                func.sum(UserStatistics.like_count).label("total_likes"),
                func.sum(UserStatistics.view_count).label("total_views"),
            )
            .filter(UserStatistics.user_id == current_user.id)
            .first()
        )

        return schemas.UserAnalytics(
            total_posts=(totals.total_posts if totals else 0) or 0,
            total_comments=(totals.total_comments if totals else 0) or 0,
            total_likes=(totals.total_likes if totals else 0) or 0,
            total_views=(totals.total_views if totals else 0) or 0,
            daily_statistics=daily_stats,
        )

    # ----- Settings -----
    def get_user_settings(self, current_user: User) -> schemas.UserSettings:
        return schemas.UserSettings(
            ui_settings=schemas.UISettings(**(current_user.ui_settings or {})),
            notifications_settings=schemas.NotificationsSettings(
                **(current_user.notifications_settings or {})
            ),
        )

    def update_user_settings(
        self, current_user: User, settings: schemas.UserSettingsUpdate
    ) -> schemas.UserSettings:
        if settings.ui_settings:
            if current_user.ui_settings is None:
                current_user.ui_settings = {}
            current_user.ui_settings.update(
                settings.ui_settings.model_dump(exclude_unset=True)
            )
        if settings.notifications_settings:
            if current_user.notifications_settings is None:
                current_user.notifications_settings = {}
            current_user.notifications_settings.update(
                settings.notifications_settings.model_dump(exclude_unset=True)
            )

        self.db.commit()
        self.db.refresh(current_user)
        return self.get_user_settings(current_user)

    def update_block_settings(
        self, current_user: User, settings: schemas.BlockSettings
    ) -> User:
        current_user.default_block_type = settings.default_block_type
        self.db.commit()
        self.db.refresh(current_user)
        return current_user

    def update_repost_settings(
        self, current_user: User, settings: schemas.UserUpdate
    ) -> User:
        if settings.allow_reposts is not None:
            current_user.allow_reposts = settings.allow_reposts
            self.db.commit()
            self.db.refresh(current_user)
        return current_user

    # ----- Enforcement -----
    def suspend_user(self, user_id: int, days: int) -> Dict[str, str]:
        user = self.get_user_or_404(user_id)
        user.is_suspended = True
        user.suspension_end_date = datetime.now(timezone.utc) + timedelta(days=days)
        self.db.commit()
        return {"message": "User suspended successfully"}

    def unsuspend_user(self, user_id: int) -> Dict[str, str]:
        user = self.get_user_or_404(user_id)
        user.is_suspended = False
        user.suspension_end_date = None
        self.db.commit()
        return {"message": "User unsuspended successfully"}

    def activate_user(self, user_id: int) -> Dict[str, str]:
        """Mark a user as active/verified and clear suspension flags."""
        user = self.get_user_or_404(user_id)
        user.is_suspended = False
        user.suspension_end_date = None
        user.is_verified = True
        self.db.commit()
        return {"message": "User activated successfully"}

    def lock_account(self, user_id: int, *, minutes: int = 30) -> Dict[str, str]:
        """Lock the account until a future time window."""
        user = self.get_user_or_404(user_id)
        user.account_locked_until = datetime.now(timezone.utc) + timedelta(
            minutes=minutes
        )
        self.db.commit()
        return {"message": "Account locked"}

    def perform_admin_action(
        self, acting_user: User, action: str = "noop"
    ) -> Dict[str, str]:
        """Ensure only admins can perform privileged actions."""
        if not getattr(acting_user, "is_admin", False):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Admin privileges required",
            )
        return {"action": action, "status": "ok"}

    def revoke_tokens(self, user: User, tokens: list[str]) -> int:
        """Blacklist provided tokens; roll back on commit errors."""
        try:
            for token in tokens:
                self.db.add(TokenBlacklist(token=token, user_id=user.id))
            self.db.commit()
            return len(tokens)
        except Exception:
            self.db.rollback()
            raise

    # ----- Logging -----
    def log_activity(self, user_id: int, activity_type: str, details: Dict) -> None:
        activity = UserActivity(
            user_id=user_id, activity_type=activity_type, details=details
        )
        self.db.add(activity)
        self.db.commit()

    # ----- Privacy-first utilities -----
    def export_user_data(self, current_user: User) -> dict:
        posts = (
            self.db.query(models.Post)
            .filter(models.Post.owner_id == current_user.id)
            .all()
        )
        comments = (
            self.db.query(models.Comment)
            .filter(models.Comment.owner_id == current_user.id)
            .all()
        )
        identities = (
            self.db.query(UserIdentity)
            .filter(UserIdentity.main_user_id == current_user.id)
            .all()
        )
        return {
            "user": {
                "id": current_user.id,
                "email": current_user.email,
                "created_at": current_user.created_at,
                "privacy_level": current_user.privacy_level,
            },
            "posts": [
                {
                    "id": p.id,
                    "title": p.title,
                    "created_at": p.created_at,
                    "is_encrypted": getattr(p, "is_encrypted", False),
                    "is_living_testimony": getattr(p, "is_living_testimony", False),
                }
                for p in posts
            ],
            "comments": [
                {
                    "id": c.id,
                    "post_id": c.post_id,
                    "content": c.content,
                    "created_at": c.created_at,
                }
                for c in comments
            ],
            "identities": identities,
        }

    def delete_account(self, current_user: User) -> None:
        self.db.delete(current_user)
        self.db.commit()

    # ----- Multi-identity management -----
    def link_identity(
        self, current_user: User, linked_user_id: int, relationship_type: str = "alias"
    ) -> UserIdentity:
        if linked_user_id == current_user.id:
            raise HTTPException(
                status_code=400, detail="Cannot link to the same account"
            )

        linked_user = self.db.query(User).filter(User.id == linked_user_id).first()
        if not linked_user:
            raise HTTPException(status_code=404, detail="Linked user not found")

        existing = (
            self.db.query(UserIdentity)
            .filter(
                UserIdentity.main_user_id == current_user.id,
                UserIdentity.linked_user_id == linked_user_id,
            )
            .first()
        )
        if existing:
            return existing

        identity = UserIdentity(
            main_user_id=current_user.id,
            linked_user_id=linked_user_id,
            relationship_type=relationship_type,
        )
        self.db.add(identity)
        self.db.commit()
        self.db.refresh(identity)
        return identity

    def list_identities(self, current_user: User) -> List[UserIdentity]:
        return (
            self.db.query(UserIdentity)
            .filter(UserIdentity.main_user_id == current_user.id)
            .all()
        )

    def remove_identity(self, current_user: User, linked_user_id: int) -> None:
        identity = (
            self.db.query(UserIdentity)
            .filter(
                UserIdentity.main_user_id == current_user.id,
                UserIdentity.linked_user_id == linked_user_id,
            )
            .first()
        )
        if not identity:
            raise HTTPException(status_code=404, detail="Identity link not found")
        self.db.delete(identity)
        self.db.commit()
