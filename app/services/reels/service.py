"""Reel service for lifecycle management, cleanup, and engagement metrics."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import List, Optional

from sqlalchemy.orm import Session

from app import models, schemas
from app.modules.community.models import CommunityMember
from fastapi import HTTPException, status


class ReelService:
    """Domain service handling lifecycle of ephemeral community reels."""

    def __init__(self, db: Session):
        self.db = db

    # ------------------------------------------------------------------
    def create_reel(
        self,
        *,
        payload: schemas.ReelCreate,
        current_user: models.User,
    ) -> models.Reel:
        self._ensure_membership(current_user.id, payload.community_id)
        now = datetime.now(timezone.utc)
        expires_at = now + timedelta(hours=payload.expires_in_hours)
        new_reel = models.Reel(
            title=payload.title,
            video_url=payload.video_url,
            description=payload.description,
            owner_id=current_user.id,
            community_id=payload.community_id,
            expires_at=expires_at,
            is_active=True,
        )
        self.db.add(new_reel)
        self.db.commit()
        self.db.refresh(new_reel)
        return new_reel

    def list_reels(
        self,
        *,
        community_id: Optional[int] = None,
        limit: int = 50,
        include_expired: bool = False,
    ) -> List[models.Reel]:
        now = datetime.now(timezone.utc)
        query = self.db.query(models.Reel).filter(models.Reel.is_active.is_(True))
        if community_id:
            query = query.filter(models.Reel.community_id == community_id)
        if not include_expired:
            query = query.filter(models.Reel.expires_at > now)
        return query.order_by(models.Reel.created_at.desc()).limit(limit).all()

    def record_view(self, *, reel_id: int) -> models.Reel:
        reel = self._get_reel_or_404(reel_id)
        if not self._is_reel_active(reel):
            raise HTTPException(
                status_code=status.HTTP_410_GONE, detail="Reel has expired"
            )
        reel.view_count += 1
        self.db.commit()
        self.db.refresh(reel)
        return reel

    def deactivate_reel(self, *, reel_id: int, current_user: models.User) -> None:
        reel = self._get_reel_or_404(reel_id)
        if reel.owner_id != current_user.id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Not authorised to delete this reel",
            )
        reel.is_active = False
        self.db.commit()

    def cleanup_expired_reels(self) -> int:
        """Archive expired reels and mark them inactive."""
        now = datetime.now(timezone.utc)
        expired = (
            self.db.query(models.Reel)
            .filter(models.Reel.is_active.is_(True), models.Reel.expires_at <= now)
            .all()
        )
        if not expired:
            return 0

        archives = [
            models.ArchivedReel(
                reel_id=reel.id,
                title=reel.title,
                video_url=reel.video_url,
                description=reel.description,
                owner_id=reel.owner_id,
                community_id=reel.community_id,
                expires_at=reel.expires_at,
                view_count=reel.view_count,
            )
            for reel in expired
        ]
        self.db.add_all(archives)

        for reel in expired:
            reel.is_active = False
        self.db.commit()
        return len(expired)

    # ------------------------------------------------------------------
    def _ensure_membership(self, user_id: int, community_id: int) -> None:
        membership = (
            self.db.query(CommunityMember)
            .filter(
                CommunityMember.user_id == user_id,
                CommunityMember.community_id == community_id,
            )
            .first()
        )
        if not membership:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="You must be a member of the community to post a reel",
            )

    def _get_reel_or_404(self, reel_id: int) -> models.Reel:
        reel = self.db.query(models.Reel).filter(models.Reel.id == reel_id).first()
        if not reel:
            raise HTTPException(status_code=404, detail="Reel not found")
        return reel

    @staticmethod
    def _is_reel_active(reel: models.Reel) -> bool:
        if not reel.is_active:
            return False
        expires_at = reel.expires_at
        if expires_at.tzinfo is None:
            expires_at = expires_at.replace(tzinfo=timezone.utc)
        return expires_at > datetime.now(timezone.utc)
