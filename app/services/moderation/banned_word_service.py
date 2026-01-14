"""Service layer for managing banned words."""

from __future__ import annotations

from typing import List, Optional

from sqlalchemy import func
from sqlalchemy.orm import Session

from app import schemas
from app.modules.moderation.models import BannedWord
from app.modules.users.models import User
from app.modules.utils.analytics import update_ban_statistics
from app.modules.utils.moderation import log_admin_action
from fastapi import HTTPException, status


class BannedWordService:
    """Encapsulates CRUD operations for banned words with auditing hooks."""

    def __init__(self, db: Session):
        self.db = db

    def add_word(
        self, *, payload: schemas.BannedWordCreate, current_user: User
    ) -> BannedWord:
        existing = (
            self.db.query(BannedWord)
            .filter(func.lower(BannedWord.word) == payload.word.lower())
            .first()
        )
        if existing:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Word already exists in the banned list",
            )

        banned_word = BannedWord(**payload.model_dump(), created_by=current_user.id)
        self.db.add(banned_word)
        self.db.commit()
        self.db.refresh(banned_word)

        update_ban_statistics(self.db, "word", "word_added", 1.0)
        log_admin_action(
            self.db, current_user.id, "add_banned_word", {"word": payload.word}
        )
        return banned_word

    def list_words(
        self,
        *,
        skip: int,
        limit: int,
        search: Optional[str],
        sort_by: str,
        sort_order: str,
    ) -> dict:
        query = self.db.query(BannedWord)
        if search:
            query = query.filter(BannedWord.word.ilike(f"%{search}%"))

        # Support stable sorting by word or creation time.
        if sort_by == "created_at":
            column = BannedWord.created_at
        else:
            column = BannedWord.word

        if sort_order == "desc":
            query = query.order_by(column.desc())
        else:
            query = query.order_by(column.asc())

        total = query.count()
        words = query.offset(skip).limit(limit).all()
        serialized = [
            schemas.BannedWordOut.model_validate(w).model_dump() for w in words
        ]
        return {"total": total, "words": serialized}

    def remove_word(self, *, word_id: int, current_user: User) -> dict:
        word = self.db.query(BannedWord).filter(BannedWord.id == word_id).first()
        if not word:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Banned word not found",
            )

        self.db.delete(word)
        self.db.commit()

        log_admin_action(
            self.db, current_user.id, "remove_banned_word", {"word_id": word_id}
        )
        return {"message": "Banned word removed successfully"}

    def update_word(
        self,
        *,
        word_id: int,
        update_payload: schemas.BannedWordUpdate,
        current_user: User,
    ) -> BannedWord:
        word = self.db.query(BannedWord).filter(BannedWord.id == word_id).first()
        if not word:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Banned word not found",
            )

        for key, value in update_payload.model_dump(exclude_unset=True).items():
            setattr(word, key, value)

        self.db.commit()
        self.db.refresh(word)

        log_admin_action(
            self.db,
            current_user.id,
            "update_banned_word",
            {
                "word_id": word_id,
                "updates": update_payload.model_dump(exclude_unset=True),
            },
        )
        return word

    def add_bulk(
        self,
        *,
        payloads: List[schemas.BannedWordCreate],
        current_user: User,
    ) -> dict:
        new_words = [
            BannedWord(**word.model_dump(), created_by=current_user.id)
            for word in payloads
        ]
        # Bulk insert keeps audit logging in one entry.
        self.db.add_all(new_words)
        self.db.commit()

        log_admin_action(
            self.db, current_user.id, "add_banned_words_bulk", {"count": len(new_words)}
        )
        return {
            "message": f"Added {len(new_words)} banned words successfully",
            "added_words": len(new_words),
        }
