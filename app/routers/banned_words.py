"""Banned words router for managing moderation wordlists with severity levels."""

from typing import List, Optional

from sqlalchemy.orm import Session

from app.core.database import get_db
from app.modules.users.models import User
from app.services.moderation import BannedWordService
from fastapi import APIRouter, Depends, HTTPException, Query, status

from .. import oauth2, schemas
from ..cache import cache

router = APIRouter(prefix="/banned-words", tags=["Banned Words"])


def get_banned_word_service(db: Session = Depends(get_db)) -> BannedWordService:
    """Return banned word service."""
    return BannedWordService(db)


def check_admin(current_user: User = Depends(oauth2.get_current_user)):
    """Endpoint: check_admin."""
    if not getattr(current_user, "is_admin", False):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access denied: admin privileges required",
        )
    return current_user


@router.post(
    "/", status_code=status.HTTP_201_CREATED, response_model=schemas.BannedWordOut
)
async def add_banned_word(
    word: schemas.BannedWordCreate,
    service: BannedWordService = Depends(get_banned_word_service),
    current_user: User = Depends(check_admin),
):
    """Add a single banned word."""
    return service.add_word(payload=word, current_user=current_user)


@router.get("/", response_model=dict)
@cache(expire=300)
async def get_banned_words(
    service: BannedWordService = Depends(get_banned_word_service),
    current_user: User = Depends(check_admin),
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=1000),
    search: Optional[str] = None,
    sort_by: Optional[str] = Query(
        "word", description="Sort by 'word' or 'created_at'"
    ),
    sort_order: Optional[str] = Query("asc", description="Sort order: 'asc' or 'desc'"),
):
    """List banned words with optional filtering/sorting."""
    return service.list_words(
        skip=skip,
        limit=limit,
        search=search,
        sort_by=sort_by or "word",
        sort_order=sort_order or "asc",
    )


@router.delete("/{word_id}", status_code=status.HTTP_200_OK)
async def remove_banned_word(
    word_id: int,
    service: BannedWordService = Depends(get_banned_word_service),
    current_user: User = Depends(check_admin),
):
    """Remove a banned word by ID."""
    return service.remove_word(word_id=word_id, current_user=current_user)


@router.put("/{word_id}", response_model=schemas.BannedWordOut)
async def update_banned_word(
    word_id: int,
    word_update: schemas.BannedWordUpdate,
    service: BannedWordService = Depends(get_banned_word_service),
    current_user: User = Depends(check_admin),
):
    """Update attributes of a banned word."""
    return service.update_word(
        word_id=word_id,
        update_payload=word_update,
        current_user=current_user,
    )


@router.post("/bulk", status_code=status.HTTP_201_CREATED)
async def add_banned_words_bulk(
    words: List[schemas.BannedWordCreate],
    service: BannedWordService = Depends(get_banned_word_service),
    current_user: User = Depends(check_admin),
):
    """Bulk-insert banned words."""
    return service.add_bulk(payloads=words, current_user=current_user)
