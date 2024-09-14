from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from .. import models, database, oauth2

router = APIRouter(prefix="/block", tags=["Block"])


@router.post("/{user_id}", status_code=status.HTTP_201_CREATED)
def block_user(
    user_id: int,
    db: Session = Depends(database.get_db),
    current_user: models.User = Depends(oauth2.get_current_user),
):
    if user_id == current_user.id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="You cannot block yourself"
        )

    # تحقق مما إذا كان المستخدم محظورًا بالفعل
    existing_block = (
        db.query(models.Block)
        .filter(
            models.Block.follower_id == current_user.id,
            models.Block.blocked_id == user_id,
        )
        .first()
    )
    if existing_block:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="User is already blocked"
        )

    block = models.Block(follower_id=current_user.id, blocked_id=user_id)
    db.add(block)
    db.commit()

    return {"message": "User successfully blocked"}


@router.delete("/{user_id}", status_code=status.HTTP_204_NO_CONTENT)
def unblock_user(
    user_id: int,
    db: Session = Depends(database.get_db),
    current_user: models.User = Depends(oauth2.get_current_user),
):
    block = (
        db.query(models.Block)
        .filter(
            models.Block.follower_id == current_user.id,
            models.Block.blocked_id == user_id,
        )
        .first()
    )

    if not block:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="User is not blocked"
        )

    db.delete(block)
    db.commit()

    return {"message": "User successfully unblocked"}
