from fastapi import APIRouter, Depends, HTTPException, status, BackgroundTasks
from sqlalchemy.orm import Session
from .. import models, database, oauth2, schemas
from datetime import datetime, timedelta
from ..celery_worker import celery_app, unblock_user

router = APIRouter(prefix="/block", tags=["Block"])


@celery_app.task
def unblock_user(blocker_id: int, blocked_id: int):
    db = database.SessionLocal()
    try:
        block = (
            db.query(models.Block)
            .filter(
                models.Block.blocker_id == blocker_id,
                models.Block.blocked_id == blocked_id,
            )
            .first()
        )
        if block:
            db.delete(block)
            db.commit()
    finally:
        db.close()


@celery_app.task
def clean_expired_blocks():
    db = database.SessionLocal()
    try:
        expired_blocks = (
            db.query(models.Block).filter(models.Block.ends_at < datetime.now()).all()
        )
        for block in expired_blocks:
            db.delete(block)
        db.commit()
    finally:
        db.close()


@router.post("/", status_code=status.HTTP_201_CREATED, response_model=schemas.BlockOut)
def block_user(
    block: schemas.BlockCreate,
    background_tasks: BackgroundTasks,
    db: Session = Depends(database.get_db),
    current_user: models.User = Depends(oauth2.get_current_user),
):
    if block.blocked_id == current_user.id:
        raise HTTPException(status_code=400, detail="You cannot block yourself")

    existing_block = (
        db.query(models.Block)
        .filter(
            models.Block.blocker_id == current_user.id,
            models.Block.blocked_id == block.blocked_id,
        )
        .first()
    )

    if existing_block:
        raise HTTPException(status_code=400, detail="User is already blocked")

    new_block = models.Block(blocker_id=current_user.id, blocked_id=block.blocked_id)

    if block.duration and block.duration_unit:
        if block.duration_unit == schemas.BlockDuration.HOURS:
            new_block.ends_at = datetime.now() + timedelta(hours=block.duration)
        elif block.duration_unit == schemas.BlockDuration.DAYS:
            new_block.ends_at = datetime.now() + timedelta(days=block.duration)
        elif block.duration_unit == schemas.BlockDuration.WEEKS:
            new_block.ends_at = datetime.now() + timedelta(weeks=block.duration)

        new_block.duration = block.duration
        new_block.duration_unit = block.duration_unit

    db.add(new_block)
    db.commit()
    db.refresh(new_block)

    if new_block.ends_at:
        background_tasks.add_task(
            unblock_user.apply_async,
            args=[current_user.id, block.blocked_id],
            eta=new_block.ends_at,
        )

    return new_block


@router.delete("/{user_id}", status_code=status.HTTP_204_NO_CONTENT)
def manual_unblock_user(
    user_id: int,
    db: Session = Depends(database.get_db),
    current_user: models.User = Depends(oauth2.get_current_user),
):
    block = (
        db.query(models.Block)
        .filter(
            models.Block.blocker_id == current_user.id,
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


@router.get("/{user_id}", response_model=schemas.BlockOut)
def get_block_info(
    user_id: int,
    db: Session = Depends(database.get_db),
    current_user: models.User = Depends(oauth2.get_current_user),
):
    block = (
        db.query(models.Block)
        .filter(
            models.Block.blocker_id == current_user.id,
            models.Block.blocked_id == user_id,
        )
        .first()
    )

    if not block:
        raise HTTPException(status_code=404, detail="Block not found")

    return block
