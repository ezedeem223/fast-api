"""
Block Router Module
This module provides endpoints for managing user blocks in the system.
It includes endpoints to block users, manually unblock them, retrieve block information,
fetch block logs and statistics, as well as handling block appeals.
"""

# =====================================================
# ==================== Imports ========================
# =====================================================
from fastapi import APIRouter, Depends, HTTPException, status, BackgroundTasks, Query
from sqlalchemy.orm import Session
from sqlalchemy import func
from typing import List, Optional
from datetime import datetime, timedelta

# Local imports
from .. import models, database, oauth2, schemas, utils
from ..celery_worker import celery_app, unblock_user

# =====================================================
# =============== Global Variables ====================
# =====================================================
router = APIRouter(prefix="/block", tags=["Block"])

# =====================================================
# ==================== Endpoints ======================
# =====================================================


@router.post("/", status_code=status.HTTP_201_CREATED, response_model=schemas.BlockOut)
def block_user(
    block: schemas.BlockCreate,
    background_tasks: BackgroundTasks,
    db: Session = Depends(database.get_db),
    current_user: models.User = Depends(oauth2.get_current_user),
):
    """
    Block a user.

    Parameters:
        - block: BlockCreate schema containing the user to block, block type, duration, etc.
        - background_tasks: Used for scheduling unblock task.
        - db: Database session.
        - current_user: The current authenticated user.

    Returns:
        The newly created block record.
    """
    # Prevent blocking self
    if block.blocked_id == current_user.id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="You cannot block yourself"
        )

    # Check if the user is already blocked
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

    # Create new block record
    new_block = models.Block(
        blocker_id=current_user.id,
        blocked_id=block.blocked_id,
        block_type=block.block_type,
    )

    # Set block duration if provided
    if block.duration and block.duration_unit:
        new_block.ends_at = datetime.now() + timedelta(
            **{block.duration_unit.value: block.duration}
        )
        new_block.duration = block.duration
        new_block.duration_unit = block.duration_unit

    db.add(new_block)

    # Log the block event in BlockLog
    block_log = models.BlockLog(
        blocker_id=current_user.id,
        blocked_id=block.blocked_id,
        block_type=block.block_type,
        reason=block.reason,
    )
    db.add(block_log)

    db.commit()
    db.refresh(new_block)

    # Schedule automatic unblock if an expiration is set
    if new_block.ends_at:
        background_tasks.add_task(
            unblock_user.apply_async,
            args=[current_user.id, block.blocked_id],
            eta=new_block.ends_at,
        )

    # Log the event using utils
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
    """
    Manually unblock a user.

    Parameters:
        - user_id: The ID of the blocked user.
        - db: Database session.
        - current_user: The current authenticated user.

    Returns:
        A message confirming the user has been unblocked.
    """
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

    # Update block log if exists
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
    """
    Get information about a specific block.

    Parameters:
        - user_id: The ID of the blocked user.
        - db: Database session.
        - current_user: The current authenticated user.

    Returns:
        The block record if found.
    """
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
    """
    Get block logs for the current user.

    Parameters:
        - skip: Number of records to skip.
        - limit: Maximum number of records to return.

    Returns:
        A list of block logs.
    """
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
    """
    Get a list of currently blocked users.

    Returns:
        A list of blocked users with details such as block type, reason, and when the block started.
    """
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
    """
    Get block statistics for the current user.

    Returns:
        A summary including total blocks, active blocks, and a distribution of block types.
    """
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
    """
    Create a new block appeal.

    Parameters:
        - appeal: BlockAppealCreate schema containing block ID and reason.
        - db: Database session.
        - current_user: The current authenticated user.

    Returns:
        The created block appeal record.
    """
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
    """
    Get a list of pending block appeals.
    Only moderators are allowed to view appeals.
    """
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
    """
    Review a block appeal.

    Only moderators can review appeals. If the appeal is approved, the corresponding block is removed.
    """
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
