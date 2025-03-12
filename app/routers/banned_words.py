"""
Banned Words Management Router
This module provides endpoints for managing banned words in the system.
It includes endpoints to add, retrieve, update, delete, and bulk add banned words.
"""

# =====================================================
# ==================== Imports ========================
# =====================================================
from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.orm import Session
from sqlalchemy import func
from typing import List, Optional

# Local imports
from .. import models, schemas, oauth2, utils
from ..database import get_db
from ..cache import cache

# =====================================================
# =============== Global Variables ====================
# =====================================================
router = APIRouter(prefix="/banned-words", tags=["Banned Words"])


# =====================================================
# ============ Dependency: Admin Check ================
# =====================================================
async def check_admin(current_user: models.User = Depends(oauth2.get_current_user)):
    """
    Dependency to verify that the current user is an admin.
    Throws an HTTP 403 error if the user is not an admin.
    """
    # Assuming utils.is_admin is an asynchronous function that returns True if the user is admin
    if not await utils.is_admin(current_user):
        raise HTTPException(
            status_code=403, detail="فقط المسؤولون يمكنهم تنفيذ هذا الإجراء"
        )
    return current_user


# =====================================================
# ==================== Endpoints ======================
# =====================================================


@router.post(
    "/", status_code=status.HTTP_201_CREATED, response_model=schemas.BannedWordOut
)
async def add_banned_word(
    word: schemas.BannedWordCreate,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(check_admin),
):
    """
    Add a new banned word.

    Parameters:
        - word: The banned word data to create.
        - db: Database session.
        - current_user: The current admin user.

    Returns:
        The created banned word information.
    """
    # Check if the word already exists (case-insensitive)
    existing_word = (
        db.query(models.BannedWord)
        .filter(func.lower(models.BannedWord.word) == word.word.lower())
        .first()
    )
    if existing_word:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="هذه الكلمة محظورة بالفعل"
        )

    # Create a new banned word record with the creator's ID
    new_banned_word = models.BannedWord(**word.dict(), created_by=current_user.id)
    db.add(new_banned_word)
    db.commit()
    db.refresh(new_banned_word)

    # Update ban statistics (for word bans)
    utils.update_ban_statistics(db, "word", "إضافة كلمة محظورة", 1.0)

    # Log the admin action
    utils.log_admin_action(db, current_user.id, "add_banned_word", {"word": word.word})

    return new_banned_word


@router.get("/", response_model=dict)
@cache(expire=300)  # Cache results for 5 minutes
async def get_banned_words(
    db: Session = Depends(get_db),
    current_user: models.User = Depends(check_admin),
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=1000),
    search: Optional[str] = None,
    sort_by: Optional[str] = Query(
        "word", description="Sort by 'word' or 'created_at'"
    ),
    sort_order: Optional[str] = Query("asc", description="Sort order: 'asc' or 'desc'"),
):
    """
    Retrieve a list of banned words with optional search and sorting.

    Parameters:
        - skip: Number of records to skip.
        - limit: Maximum number of records to return.
        - search: Search text for banned words.
        - sort_by: Field to sort by ('word' or 'created_at').
        - sort_order: Sort order ('asc' for ascending, 'desc' for descending).

    Returns:
        A dictionary with total count and list of banned words.
    """
    query = db.query(models.BannedWord)

    # Apply search filter if provided
    if search:
        query = query.filter(models.BannedWord.word.ilike(f"%{search}%"))

    # Apply sorting
    if sort_by == "word":
        query = query.order_by(
            models.BannedWord.word.asc()
            if sort_order == "asc"
            else models.BannedWord.word.desc()
        )
    elif sort_by == "created_at":
        query = query.order_by(
            models.BannedWord.created_at.asc()
            if sort_order == "asc"
            else models.BannedWord.created_at.desc()
        )

    total = query.count()
    words = query.offset(skip).limit(limit).all()

    return {"total": total, "words": words}


@router.delete("/{word_id}", status_code=status.HTTP_204_NO_CONTENT)
async def remove_banned_word(
    word_id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(check_admin),
):
    """
    Remove a banned word by its ID.

    Parameters:
        - word_id: The ID of the banned word.
        - db: Database session.
        - current_user: The current admin user.

    Returns:
        A message confirming successful removal.
    """
    word = db.query(models.BannedWord).filter(models.BannedWord.id == word_id).first()
    if not word:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="الكلمة المحظورة غير موجودة"
        )
    db.delete(word)
    db.commit()

    utils.log_admin_action(
        db, current_user.id, "remove_banned_word", {"word_id": word_id}
    )
    return {"message": "تمت إزالة الكلمة المحظورة بنجاح"}


@router.put("/{word_id}", response_model=schemas.BannedWordOut)
async def update_banned_word(
    word_id: int,
    word_update: schemas.BannedWordUpdate,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(check_admin),
):
    """
    Update a banned word.

    Parameters:
        - word_id: The ID of the banned word.
        - word_update: The update data.
        - db: Database session.
        - current_user: The current admin user.

    Returns:
        The updated banned word.
    """
    word = db.query(models.BannedWord).filter(models.BannedWord.id == word_id).first()
    if not word:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="الكلمة المحظورة غير موجودة"
        )
    for key, value in word_update.dict(exclude_unset=True).items():
        setattr(word, key, value)
    db.commit()
    db.refresh(word)

    utils.log_admin_action(
        db,
        current_user.id,
        "update_banned_word",
        {"word_id": word_id, "updates": word_update.dict(exclude_unset=True)},
    )
    return word


@router.post("/bulk", status_code=status.HTTP_201_CREATED)
async def add_banned_words_bulk(
    words: List[schemas.BannedWordCreate],
    db: Session = Depends(get_db),
    current_user: models.User = Depends(check_admin),
):
    """
    Bulk add banned words.

    Parameters:
        - words: A list of banned words to add.
        - db: Database session.
        - current_user: The current admin user.

    Returns:
        A message and the count of added words.
    """
    new_words = [
        models.BannedWord(**word.dict(), created_by=current_user.id) for word in words
    ]
    db.add_all(new_words)
    db.commit()

    utils.log_admin_action(
        db, current_user.id, "add_banned_words_bulk", {"count": len(new_words)}
    )

    return {
        "message": f"تمت إضافة {len(new_words)} كلمة محظورة بنجاح",
        "added_words": len(new_words),
    }
