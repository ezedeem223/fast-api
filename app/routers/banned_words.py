from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.orm import Session
from sqlalchemy import func
from .. import models, schemas, oauth2, utils
from ..database import get_db
from typing import List, Optional
from ..cache import cache

router = APIRouter(prefix="/banned-words", tags=["Banned Words"])


async def check_admin(current_user: models.User = Depends(oauth2.get_current_user)):
    if not await utils.is_admin(current_user):
        raise HTTPException(
            status_code=403, detail="Only administrators can perform this action"
        )
    return current_user


@router.post(
    "/", status_code=status.HTTP_201_CREATED, response_model=schemas.BannedWordOut
)
async def add_banned_word(
    word: schemas.BannedWordCreate,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(check_admin),
):
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


@router.get("/", response_model=schemas.BannedWordListOut)
@cache(expire=300)
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
async def remove_banned_word(
    word_id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(check_admin),
):
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
async def update_banned_word(
    word_id: int,
    word_update: schemas.BannedWordUpdate,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(check_admin),
):
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


@router.post("/bulk", status_code=status.HTTP_201_CREATED)
async def add_banned_words_bulk(
    words: List[schemas.BannedWordCreate],
    db: Session = Depends(get_db),
    current_user: models.User = Depends(check_admin),
):
    new_words = [
        models.BannedWord(**word.dict(), created_by=current_user.id) for word in words
    ]
    db.add_all(new_words)
    db.commit()

    utils.log_admin_action(
        db, current_user.id, "add_banned_words_bulk", {"count": len(new_words)}
    )

    return {"message": f"{len(new_words)} words added successfully"}
