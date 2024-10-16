from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from .. import models, schemas, oauth2, utils
from ..database import get_db
from typing import List

router = APIRouter(prefix="/banned-words", tags=["Banned Words"])


@router.post(
    "/", status_code=status.HTTP_201_CREATED, response_model=schemas.BannedWordOut
)
def add_banned_word(
    word: schemas.BannedWordCreate,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(oauth2.get_current_user),
):
    if not current_user.is_admin:
        raise HTTPException(
            status_code=403, detail="Not authorized to add banned words"
        )

    existing_word = (
        db.query(models.BannedWord).filter(models.BannedWord.word == word.word).first()
    )
    if existing_word:
        raise HTTPException(status_code=400, detail="This word is already banned")

    new_banned_word = models.BannedWord(**word.dict(), created_by=current_user.id)
    db.add(new_banned_word)
    db.commit()
    db.refresh(new_banned_word)

    utils.update_ban_statistics(
        db, "word", "Added banned word", 1.0
    )  # افتراض فعالية أولية 1.0

    return new_banned_word


@router.get("/", response_model=List[schemas.BannedWordOut])
def get_banned_words(
    db: Session = Depends(get_db),
    current_user: models.User = Depends(oauth2.get_current_user),
):
    if not current_user.is_admin:
        raise HTTPException(
            status_code=403, detail="Not authorized to view banned words"
        )

    return db.query(models.BannedWord).all()


@router.delete("/{word_id}", status_code=status.HTTP_204_NO_CONTENT)
def remove_banned_word(
    word_id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(oauth2.get_current_user),
):
    if not current_user.is_admin:
        raise HTTPException(
            status_code=403, detail="Not authorized to remove banned words"
        )

    word = db.query(models.BannedWord).filter(models.BannedWord.id == word_id).first()
    if not word:
        raise HTTPException(status_code=404, detail="Banned word not found")

    db.delete(word)
    db.commit()
    return {"message": "Banned word removed successfully"}


@router.put("/{word_id}", response_model=schemas.BannedWordOut)
def update_banned_word(
    word_id: int,
    word_update: schemas.BannedWordUpdate,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(oauth2.get_current_user),
):
    if not current_user.is_admin:
        raise HTTPException(
            status_code=403, detail="Not authorized to update banned words"
        )

    word = db.query(models.BannedWord).filter(models.BannedWord.id == word_id).first()
    if not word:
        raise HTTPException(status_code=404, detail="Banned word not found")

    for key, value in word_update.dict(exclude_unset=True).items():
        setattr(word, key, value)

    db.commit()
    db.refresh(word)
    return word
