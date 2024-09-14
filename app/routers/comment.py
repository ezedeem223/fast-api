from fastapi import FastAPI, HTTPException, status, Depends, APIRouter, BackgroundTasks
from sqlalchemy.orm import Session
from .. import models, schemas, oauth2
from ..database import get_db
from typing import List
from ..notifications import send_email_notification

router = APIRouter(prefix="/comments", tags=["Comments"])


@router.post("/", status_code=status.HTTP_201_CREATED, response_model=schemas.Comment)
def create_comment(
    background_tasks: BackgroundTasks,
    comment: schemas.CommentCreate,
    db: Session = Depends(get_db),
    current_user: int = Depends(oauth2.get_current_user),
):
    # تحقق من إذا كان المستخدم موثقًا
    if not current_user.is_verified:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="User is not verified."
        )

    post = db.query(models.Post).filter(models.Post.id == comment.post_id).first()
    if not post:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Post not found"
        )

    new_comment = models.Comment(
        owner_id=current_user.id, post_id=comment.post_id, **comment.dict()
    )
    db.add(new_comment)
    db.commit()
    db.refresh(new_comment)

    # إرسال إشعار بالبريد الإلكتروني عند إنشاء تعليق جديد
    post_owner_email = (
        db.query(models.User.email).filter(models.User.id == post.owner_id).scalar()
    )
    send_email_notification(
        background_tasks=background_tasks,
        to=[post_owner_email],
        subject="New Comment on Your Post",
        body=f"A new comment has been added to your post titled '{post.title}'.",
    )

    return new_comment


@router.get("/{post_id}", response_model=List[schemas.Comment])
def get_comments(
    post_id: int,
    db: Session = Depends(get_db),
    current_user: int = Depends(oauth2.get_current_user),
):
    post = db.query(models.Post).filter(models.Post.id == post_id).first()
    if not post:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Post not found"
        )
    comments = db.query(models.Comment).filter(models.Comment.post_id == post_id).all()
    return comments


@router.post(
    "/report", status_code=status.HTTP_201_CREATED, response_model=schemas.Report
)
def report_comment(
    report: schemas.ReportCreate,
    db: Session = Depends(get_db),
    current_user: int = Depends(oauth2.get_current_user),
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
