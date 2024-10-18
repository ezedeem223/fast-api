from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.orm import Session
from sqlalchemy import func
from .. import models, schemas, oauth2, utils
from ..database import get_db
from typing import List, Optional

router = APIRouter(prefix="/banned-words", tags=["Banned Words"])


def check_admin(current_user: models.User):
    if not current_user.is_admin:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Not authorized to perform this action",
        )


@router.post(
    "/", status_code=status.HTTP_201_CREATED, response_model=schemas.BannedWordOut
)
def add_banned_word(
    word: schemas.BannedWordCreate,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(oauth2.get_current_user),
):
    """
    Add a new banned word to the database.
    """
    check_admin(current_user)

    existing_word = (
        db.query(models.BannedWord)
        .filter(func.lower(models.BannedWord.word) == word.word.lower())
        .first()
    )
    if existing_word:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="This word is already banned",
        )

    new_banned_word = models.BannedWord(**word.dict(), created_by=current_user.id)
    db.add(new_banned_word)
    db.commit()
    db.refresh(new_banned_word)

    utils.update_ban_statistics(db, "word", "Added banned word", 1.0)
    utils.log_admin_action(db, current_user.id, "add_banned_word", {"word": word.word})

    return new_banned_word


@router.get("/", response_model=List[schemas.BannedWordOut])
def get_banned_words(
    db: Session = Depends(get_db),
    current_user: models.User = Depends(oauth2.get_current_user),
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=1000),
    search: Optional[str] = None,
    sort_by: Optional[str] = Query(
        "word", description="Sort by 'word' or 'created_at'"
    ),
    sort_order: Optional[str] = Query("asc", description="Sort order: 'asc' or 'desc'"),
):
    """
    Retrieve a list of banned words with optional filtering and sorting.
    """
    check_admin(current_user)

    query = db.query(models.BannedWord)

    if search:
        query = query.filter(models.BannedWord.word.ilike(f"%{search}%"))

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
def remove_banned_word(
    word_id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(oauth2.get_current_user),
):
    """
    Remove a banned word from the database.
    """
    check_admin(current_user)

    word = db.query(models.BannedWord).filter(models.BannedWord.id == word_id).first()
    if not word:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Banned word not found"
        )

    db.delete(word)
    db.commit()

    utils.log_admin_action(
        db, current_user.id, "remove_banned_word", {"word_id": word_id}
    )

    return {"message": "Banned word removed successfully"}


@router.put("/{word_id}", response_model=schemas.BannedWordOut)
def update_banned_word(
    word_id: int,
    word_update: schemas.BannedWordUpdate,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(oauth2.get_current_user),
):
    """
    Update a banned word in the database.
    """
    check_admin(current_user)

    word = db.query(models.BannedWord).filter(models.BannedWord.id == word_id).first()
    if not word:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Banned word not found"
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
