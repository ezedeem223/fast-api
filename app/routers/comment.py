from fastapi import FastAPI, HTTPException, status, Depends, APIRouter, BackgroundTasks
from sqlalchemy.orm import Session, joinedload
from .. import models, schemas, oauth2
from ..database import get_db
from typing import List
from ..notifications import send_email_notification
from ..utils import check_content_against_rules
from datetime import datetime, timedelta
from ..config import settings

router = APIRouter(prefix="/comments", tags=["Comments"])

EDIT_WINDOW = timedelta(minutes=settings.COMMENT_EDIT_WINDOW_MINUTES)


def check_comment_owner(comment: models.Comment, user: models.User):
    if comment.owner_id != user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Not authorized to perform requested action",
        )


@router.post("/", status_code=status.HTTP_201_CREATED, response_model=schemas.Comment)
async def create_comment(
    background_tasks: BackgroundTasks,
    comment: schemas.CommentCreate,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(oauth2.get_current_user),
):
    if not current_user.is_verified:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="User is not verified."
        )

    post = db.query(models.Post).filter(models.Post.id == comment.post_id).first()
    if not post:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Post not found"
        )

    # التحقق من قواعد المجتمع
    if post.community_id:
        community = (
            db.query(models.Community)
            .filter(models.Community.id == post.community_id)
            .first()
        )
        rules = [rule.rule for rule in community.rules]
        if not check_content_against_rules(comment.content, rules):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Comment content violates community rules",
            )

    # التحقق من وجود التعليق الأصلي إذا كان هذا رداً
    if comment.parent_id:
        parent_comment = (
            db.query(models.Comment)
            .filter(models.Comment.id == comment.parent_id)
            .first()
        )
        if not parent_comment:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail="Parent comment not found"
            )
        if parent_comment.post_id != comment.post_id:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Parent comment does not belong to the same post",
            )

    new_comment = models.Comment(
        owner_id=current_user.id,
        post_id=comment.post_id,
        parent_id=comment.parent_id,
        **comment.model_dump(exclude={"parent_id"}),
    )
    db.add(new_comment)
    db.commit()
    db.refresh(new_comment)

    post_owner_email = (
        db.query(models.User.email).filter(models.User.id == post.owner_id).scalar()
    )
    await send_email_notification(
        to=post_owner_email,
        subject="New Comment on Your Post",
        body=f"A new comment has been added to your post titled '{post.title}'.",
    )

    return new_comment


@router.get("/{post_id}", response_model=List[schemas.Comment])
def get_comments(
    post_id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(oauth2.get_current_user),
):
    post = db.query(models.Post).filter(models.Post.id == post_id).first()
    if not post:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Post not found"
        )
    comments = (
        db.query(models.Comment)
        .filter(models.Comment.post_id == post_id, models.Comment.parent_id == None)
        .options(joinedload(models.Comment.replies))
        .all()
    )
    return comments


@router.get("/{comment_id}/replies", response_model=List[schemas.Comment])
def get_comment_replies(
    comment_id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(oauth2.get_current_user),
):
    comment = db.query(models.Comment).filter(models.Comment.id == comment_id).first()
    if not comment:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Comment not found"
        )
    return comment.replies


@router.put("/{comment_id}", response_model=schemas.Comment)
def update_comment(
    comment_id: int,
    updated_comment: schemas.CommentUpdate,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(oauth2.get_current_user),
):
    comment = db.query(models.Comment).filter(models.Comment.id == comment_id).first()
    if not comment:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Comment not found"
        )

    check_comment_owner(comment, current_user)

    if datetime.now(comment.created_at.tzinfo) - comment.created_at > EDIT_WINDOW:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="Edit window has expired"
        )

    edit_history = models.CommentEditHistory(
        comment_id=comment.id, previous_content=comment.content
    )
    db.add(edit_history)

    comment.content = updated_comment.content
    comment.is_edited = True
    comment.edited_at = datetime.now(comment.created_at.tzinfo)

    db.commit()
    db.refresh(comment)
    return comment


@router.delete("/{comment_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_comment(
    comment_id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(oauth2.get_current_user),
):
    comment = db.query(models.Comment).filter(models.Comment.id == comment_id).first()
    if not comment:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Comment not found"
        )

    check_comment_owner(comment, current_user)

    comment.is_deleted = True
    comment.deleted_at = datetime.now(comment.created_at.tzinfo)
    comment.content = "[Deleted]"

    db.commit()
    return {"message": "Comment deleted successfully"}


@router.get("/{comment_id}/history", response_model=List[schemas.CommentEditHistoryOut])
def get_comment_edit_history(
    comment_id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(oauth2.get_current_user),
):
    comment = db.query(models.Comment).filter(models.Comment.id == comment_id).first()
    if not comment:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Comment not found"
        )

    # Проверка прав доступа к истории изменений
    if current_user.id != comment.owner_id and not current_user.is_moderator:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Not authorized to view comment history",
        )

    return comment.edit_history


@router.post(
    "/report", status_code=status.HTTP_201_CREATED, response_model=schemas.Report
)
def report_comment(
    report: schemas.ReportCreate,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(oauth2.get_current_user),
):
    if report.post_id:
        post = db.query(models.Post).filter(models.Post.id == report.post_id).first()
        if not post:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail="Post not found"
            )

    if report.comment_id:
        comment = (
            db.query(models.Comment)
            .filter(models.Comment.id == report.comment_id)
            .first()
        )
        if not comment:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail="Comment not found"
            )

    new_report = models.Report(
        reporter_id=current_user.id,
        post_id=report.post_id,
        comment_id=report.comment_id,
        report_reason=report.report_reason,
    )
    db.add(new_report)
    db.commit()
    db.refresh(new_report)
    return new_report
