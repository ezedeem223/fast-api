from fastapi import APIRouter, Depends, HTTPException, status, BackgroundTasks, Query
from sqlalchemy.orm import Session
from sqlalchemy import func
from typing import List, Optional
from .. import models, database, oauth2, schemas, utils
from datetime import datetime, timedelta
from ..celery_worker import celery_app, unblock_user

router = APIRouter(prefix="/block", tags=["Block"])


@celery_app.task
def unblock_user(blocker_id: int, blocked_id: int):
    """Celery task to unblock a user after a specified duration."""
    with database.SessionLocal() as db:
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
            utils.log_event(
                db, "unblock_user", {"blocker_id": blocker_id, "blocked_id": blocked_id}
            )


@celery_app.task
def clean_expired_blocks():
    """Celery task to clean expired blocks."""
    with database.SessionLocal() as db:
        expired_blocks = (
            db.query(models.Block).filter(models.Block.ends_at < datetime.now()).all()
        )
        for block in expired_blocks:
            db.delete(block)
        db.commit()
        utils.log_event(db, "clean_expired_blocks", {"count": len(expired_blocks)})


@router.post("/", status_code=status.HTTP_201_CREATED, response_model=schemas.BlockOut)
def block_user(
    block: schemas.BlockCreate,
    background_tasks: BackgroundTasks,
    db: Session = Depends(database.get_db),
    current_user: models.User = Depends(oauth2.get_current_user),
):
    """Block a user."""
    if block.blocked_id == current_user.id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="You cannot block yourself"
        )

    existing_block = (
        db.query(models.Block)
        .filter(
            models.Block.blocker_id == current_user.id,
            models.Block.blocked_id == block.blocked_id,
        )
        .first()
    )

    if existing_block:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="User is already blocked"
        )

    new_block = models.Block(
        blocker_id=current_user.id,
        blocked_id=block.blocked_id,
        block_type=block.block_type,
    )

    if block.duration and block.duration_unit:
        new_block.ends_at = datetime.now() + timedelta(
            **{block.duration_unit.value: block.duration}
        )
        new_block.duration = block.duration
        new_block.duration_unit = block.duration_unit

    db.add(new_block)

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

    utils.log_event(
        db,
        "block_user",
        {"blocker_id": current_user.id, "blocked_id": block.blocked_id},
    )
    return new_block


@router.delete("/{user_id}", status_code=status.HTTP_204_NO_CONTENT)
def manual_unblock_user(
    user_id: int,
    db: Session = Depends(database.get_db),
    current_user: models.User = Depends(oauth2.get_current_user),
):
    """Manually unblock a user."""
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

    utils.log_event(
        db,
        "manual_unblock_user",
        {"blocker_id": current_user.id, "blocked_id": user_id},
    )
    return {"message": "User successfully unblocked"}


@router.get("/{user_id}", response_model=schemas.BlockOut)
def get_block_info(
    user_id: int,
    db: Session = Depends(database.get_db),
    current_user: models.User = Depends(oauth2.get_current_user),
):
    """Get information about a specific block."""
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
            status_code=status.HTTP_404_NOT_FOUND, detail="Block not found"
        )

    return block


@router.get("/logs", response_model=List[schemas.BlockLogOut])
def get_block_logs(
    db: Session = Depends(database.get_db),
    current_user: models.User = Depends(oauth2.get_current_user),
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=1000),
):
    """Get block logs for the current user."""
    logs = (
        db.query(models.BlockLog)
        .filter(
            (models.BlockLog.blocker_id == current_user.id)
            | (models.BlockLog.blocked_id == current_user.id)
        )
        .order_by(models.BlockLog.created_at.desc())
        .offset(skip)
        .limit(limit)
        .all()
    )
    return logs


@router.get("/current", response_model=List[schemas.BlockedUserOut])
def get_currently_blocked_users(
    db: Session = Depends(database.get_db),
    current_user: models.User = Depends(oauth2.get_current_user),
):
    """Get a list of currently blocked users."""
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
    """Get block statistics for the current user."""
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
    db: Session = Depends(database.get_db),
    current_user: models.User = Depends(oauth2.get_current_user),
):
    """Create a new block appeal."""
    block = db.query(models.Block).filter(models.Block.id == appeal.block_id).first()
    if not block:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Block not found"
        )

    if block.blocked_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You can only appeal your own blocks",
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
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="An appeal for this block is already pending",
        )

    new_appeal = models.BlockAppeal(
        block_id=appeal.block_id, user_id=current_user.id, reason=appeal.reason
    )
    db.add(new_appeal)
    db.commit()
    db.refresh(new_appeal)

    utils.log_event(
        db,
        "create_block_appeal",
        {"user_id": current_user.id, "block_id": appeal.block_id},
    )
    return new_appeal


@router.get("/appeals", response_model=List[schemas.BlockAppealOut])
def get_block_appeals(
    db: Session = Depends(database.get_db),
    current_user: models.User = Depends(oauth2.get_current_user),
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=1000),
):
    """Get a list of pending block appeals."""
    if not current_user.is_moderator:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only moderators can view appeals",
        )

    appeals = (
        db.query(models.BlockAppeal)
        .filter(models.BlockAppeal.status == models.AppealStatus.PENDING)
        .offset(skip)
        .limit(limit)
        .all()
    )
    return appeals


@router.put("/appeal/{appeal_id}", response_model=schemas.BlockAppealOut)
def review_block_appeal(
    appeal_id: int,
    review: schemas.BlockAppealReview,
    db: Session = Depends(database.get_db),
    current_user: models.User = Depends(oauth2.get_current_user),
):
    """Review a block appeal."""
    if not current_user.is_moderator:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only moderators can review appeals",
        )

    appeal = (
        db.query(models.BlockAppeal).filter(models.BlockAppeal.id == appeal_id).first()
    )
    if not appeal:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Appeal not found"
        )

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

    utils.log_event(
        db,
        "review_block_appeal",
        {
            "moderator_id": current_user.id,
            "appeal_id": appeal_id,
            "status": review.status,
        },
    )
    return appeal
