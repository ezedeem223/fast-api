from fastapi import APIRouter, Depends, HTTPException, status, BackgroundTasks
from sqlalchemy.orm import Session
from typing import List
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

    new_block = models.Block(
        blocker_id=current_user.id,
        blocked_id=block.blocked_id,
        block_type=block.block_type,
    )

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

    # Create a new block log
    block_log = models.BlockLog(
        blocker_id=current_user.id,
        blocked_id=block.blocked_id,
        block_type=block.block_type,
        reason=block.reason,
    )
    db.add(block_log)

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

    # Update the block log
    block_log = (
        db.query(models.BlockLog)
        .filter(
            models.BlockLog.blocker_id == current_user.id,
            models.BlockLog.blocked_id == user_id,
            models.BlockLog.ended_at.is_(None),
        )
        .first()
    )

    if block_log:
        block_log.ended_at = datetime.now()

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


@router.get("/logs", response_model=List[schemas.BlockLogOut])
def get_block_logs(
    db: Session = Depends(database.get_db),
    current_user: models.User = Depends(oauth2.get_current_user),
):
    logs = (
        db.query(models.BlockLog)
        .filter(
            (models.BlockLog.blocker_id == current_user.id)
            | (models.BlockLog.blocked_id == current_user.id)
        )
        .order_by(models.BlockLog.created_at.desc())
        .all()
    )
    return logs


@router.get("/current", response_model=List[schemas.BlockedUserOut])
def get_currently_blocked_users(
    db: Session = Depends(database.get_db),
    current_user: models.User = Depends(oauth2.get_current_user),
):
    blocked_users = (
        db.query(models.User, models.Block)
        .join(models.Block, models.User.id == models.Block.blocked_id)
        .filter(
            models.Block.blocker_id == current_user.id,
            (models.Block.ends_at > datetime.now()) | (models.Block.ends_at.is_(None)),
        )
        .all()
    )

    return [
        schemas.BlockedUserOut(
            id=user.id,
            username=user.username,
            email=user.email,
            block_type=block.block_type,
            reason=block.reason,
            blocked_since=block.created_at,
        )
        for user, block in blocked_users
    ]


@router.get("/statistics", response_model=schemas.BlockStatistics)
def get_block_statistics(
    db: Session = Depends(database.get_db),
    current_user: models.User = Depends(oauth2.get_current_user),
):
    total_blocks = (
        db.query(models.Block)
        .filter(models.Block.blocker_id == current_user.id)
        .count()
    )
    active_blocks = (
        db.query(models.Block)
        .filter(
            models.Block.blocker_id == current_user.id,
            (models.Block.ends_at > datetime.now()) | (models.Block.ends_at.is_(None)),
        )
        .count()
    )
    block_types = (
        db.query(models.Block.block_type, func.count(models.Block.id).label("count"))
        .filter(models.Block.blocker_id == current_user.id)
        .group_by(models.Block.block_type)
        .all()
    )

    return schemas.BlockStatistics(
        total_blocks=total_blocks,
        active_blocks=active_blocks,
        block_types={block_type: count for block_type, count in block_types},
    )


@router.post(
    "/appeal",
    status_code=status.HTTP_201_CREATED,
    response_model=schemas.BlockAppealOut,
)
def create_block_appeal(
    appeal: schemas.BlockAppealCreate,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(oauth2.get_current_user),
):
    block = db.query(models.Block).filter(models.Block.id == appeal.block_id).first()
    if not block:
        raise HTTPException(status_code=404, detail="Block not found")

    if block.blocked_id != current_user.id:
        raise HTTPException(
            status_code=403, detail="You can only appeal your own blocks"
        )

    existing_appeal = (
        db.query(models.BlockAppeal)
        .filter(
            models.BlockAppeal.block_id == appeal.block_id,
            models.BlockAppeal.status == models.AppealStatus.PENDING,
        )
        .first()
    )

    if existing_appeal:
        raise HTTPException(
            status_code=400, detail="An appeal for this block is already pending"
        )

    new_appeal = models.BlockAppeal(
        block_id=appeal.block_id, user_id=current_user.id, reason=appeal.reason
    )
    db.add(new_appeal)
    db.commit()
    db.refresh(new_appeal)

    return new_appeal


@router.get("/appeals", response_model=List[schemas.BlockAppealOut])
def get_block_appeals(
    db: Session = Depends(get_db),
    current_user: models.User = Depends(oauth2.get_current_user),
):
    if not current_user.is_moderator:
        raise HTTPException(status_code=403, detail="Only moderators can view appeals")

    appeals = (
        db.query(models.BlockAppeal)
        .filter(models.BlockAppeal.status == models.AppealStatus.PENDING)
        .all()
    )
    return appeals


@router.put("/appeal/{appeal_id}", response_model=schemas.BlockAppealOut)
def review_block_appeal(
    appeal_id: int,
    review: schemas.BlockAppealReview,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(oauth2.get_current_user),
):
    if not current_user.is_moderator:
        raise HTTPException(
            status_code=403, detail="Only moderators can review appeals"
        )

    appeal = (
        db.query(models.BlockAppeal).filter(models.BlockAppeal.id == appeal_id).first()
    )
    if not appeal:
        raise HTTPException(status_code=404, detail="Appeal not found")

    appeal.status = review.status
    appeal.reviewed_at = datetime.now()
    appeal.reviewer_id = current_user.id

    if review.status == models.AppealStatus.APPROVED:
        block = (
            db.query(models.Block).filter(models.Block.id == appeal.block_id).first()
        )
        if block:
            db.delete(block)

    db.commit()
    db.refresh(appeal)

    return appeal
