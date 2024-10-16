from fastapi import (
    FastAPI,
    HTTPException,
    status,
    Depends,
    APIRouter,
    BackgroundTasks,
    Query,
)
from sqlalchemy.orm import Session, joinedload
from sqlalchemy import desc, asc
from .. import models, schemas, oauth2
from ..database import get_db
from typing import List, Optional
from ..notifications import send_email_notification
from ..utils import check_content_against_rules, check_for_profanity, validate_urls
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
        content=comment.content,
    )

    # فحص المحتوى غير اللائق والروابط
    new_comment.contains_profanity = check_for_profanity(comment.content)
    new_comment.has_invalid_urls = not validate_urls(comment.content)

    # إذا كان هناك محتوى غير لائق أو روابط غير صالحة، نضع علامة على التعليق
    if new_comment.contains_profanity or new_comment.has_invalid_urls:
        new_comment.is_flagged = True
        new_comment.flag_reason = "Automatic content check"

        # إرسال إشعار للمشرفين
        moderators = db.query(models.User).filter(models.User.role == "moderator").all()
        for moderator in moderators:
            background_tasks.add_task(
                send_email_notification,
                to=moderator.email,
                subject="New flagged comment",
                body=f"A new comment has been automatically flagged. Comment ID: {new_comment.id}",
            )

    db.add(new_comment)
    db.commit()
    db.refresh(new_comment)

    # إرسال إشعار لصاحب المنشور
    background_tasks.add_task(
        send_email_notification,
        to=post.owner.email,
        subject="New Comment on Your Post",
        body=f"A new comment has been added to your post titled '{post.title}'.",
    )

    return new_comment


@router.get("/{post_id}", response_model=List[schemas.CommentOut])
def get_comments(
    post_id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(oauth2.get_current_user),
    sort_by: Optional[str] = Query("created_at", enum=["created_at", "likes_count"]),
    sort_order: Optional[str] = Query("desc", enum=["asc", "desc"]),
    skip: int = 0,
    limit: int = 100,
):
    post = db.query(models.Post).filter(models.Post.id == post_id).first()
    if not post:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Post not found"
        )

    query = db.query(models.Comment).filter(
        models.Comment.post_id == post_id, models.Comment.parent_id == None
    )

    # تطبيق الترتيب
    if sort_by == "created_at":
        query = query.order_by(
            desc(models.Comment.created_at)
            if sort_order == "desc"
            else asc(models.Comment.created_at)
        )
    elif sort_by == "likes_count":
        query = query.order_by(
            desc(models.Comment.likes_count)
            if sort_order == "desc"
            else asc(models.Comment.likes_count)
        )

    # تصفية التعليقات المسيئة للمستخدمين العاديين
    if not current_user.is_moderator:
        query = query.filter(models.Comment.is_flagged == False)

    comments = (
        query.options(joinedload(models.Comment.replies))
        .offset(skip)
        .limit(limit)
        .all()
    )
    return comments


@router.get("/{comment_id}/replies", response_model=List[schemas.CommentOut])
def get_comment_replies(
    comment_id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(oauth2.get_current_user),
    sort_by: Optional[str] = Query("created_at", enum=["created_at", "likes_count"]),
    sort_order: Optional[str] = Query("desc", enum=["asc", "desc"]),
):
    comment = db.query(models.Comment).filter(models.Comment.id == comment_id).first()
    if not comment:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Comment not found"
        )

    query = db.query(models.Comment).filter(models.Comment.parent_id == comment_id)

    # تطبيق الترتيب
    if sort_by == "created_at":
        query = query.order_by(
            desc(models.Comment.created_at)
            if sort_order == "desc"
            else asc(models.Comment.created_at)
        )
    elif sort_by == "likes_count":
        query = query.order_by(
            desc(models.Comment.likes_count)
            if sort_order == "desc"
            else asc(models.Comment.likes_count)
        )

    # تصفية التعليقات المسيئة للمستخدمين العاديين
    if not current_user.is_moderator:
        query = query.filter(models.Comment.is_flagged == False)

    replies = query.all()
    return replies


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

    # التحقق من صلاحيات الوصول إلى سجل التعديلات
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
    background_tasks: BackgroundTasks = BackgroundTasks(),
):
    if report.post_id:
        post = db.query(models.Post).filter(models.Post.id == report.post_id).first()
        if not post:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail="Post not found"
            )
        reported_content = post.content
        reported_type = "post"
    elif report.comment_id:
        comment = (
            db.query(models.Comment)
            .filter(models.Comment.id == report.comment_id)
            .first()
        )
        if not comment:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail="Comment not found"
            )
        reported_content = comment.content
        reported_type = "comment"
    else:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Either post_id or comment_id must be provided",
        )

    # Проверка содержимого на нецензурную лексику и недопустимые URL
    contains_profanity = utils.check_for_profanity(reported_content)
    has_invalid_urls = not utils.validate_urls(reported_content)

    new_report = models.Report(
        reporter_id=current_user.id,
        post_id=report.post_id,
        comment_id=report.comment_id,
        report_reason=report.report_reason,
        contains_profanity=contains_profanity,
        has_invalid_urls=has_invalid_urls,
    )
    db.add(new_report)
    db.commit()
    db.refresh(new_report)

    # Автоматическая пометка контента, если обнаружены нарушения
    if contains_profanity or has_invalid_urls:
        if reported_type == "post":
            post.is_flagged = True
            post.flag_reason = "Automatic content check"
        else:
            comment.is_flagged = True
            comment.flag_reason = "Automatic content check"
        db.commit()

        # Отправка уведомления модераторам
        moderators = db.query(models.User).filter(models.User.role == "moderator").all()
        for moderator in moderators:
            background_tasks.add_task(
                send_email_notification,
                to=moderator.email,
                subject=f"New flagged {reported_type}",
                body=f"A {reported_type} has been automatically flagged. {reported_type.capitalize()} ID: {report.post_id or report.comment_id}",
            )

    return new


@router.post("/{comment_id}/flag", status_code=status.HTTP_200_OK)
def flag_comment(
    comment_id: int,
    flag_reason: schemas.FlagCommentRequest,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(oauth2.get_current_user),
):
    comment = db.query(models.Comment).filter(models.Comment.id == comment_id).first()
    if not comment:
        raise HTTPException(status_code=404, detail="Comment not found")

    comment.is_flagged = True
    comment.flag_reason = flag_reason.flag_reason
    db.commit()
    return {"message": "Comment flagged successfully"}


@router.post("/{comment_id}/like", status_code=status.HTTP_200_OK)
def like_comment(
    comment_id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(oauth2.get_current_user),
):
    comment = db.query(models.Comment).filter(models.Comment.id == comment_id).first()
    if not comment:
        raise HTTPException(status_code=404, detail="Comment not found")

    comment.likes_count += 1
    db.commit()
    return {"message": "Comment liked successfully"}


@router.put("/{comment_id}/highlight", response_model=schemas.CommentOut)
def highlight_comment(
    comment_id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(oauth2.get_current_user),
):
    comment = db.query(models.Comment).filter(models.Comment.id == comment_id).first()
    if not comment:
        raise HTTPException(status_code=404, detail="Comment not found")

    post = db.query(models.Post).filter(models.Post.id == comment.post_id).first()
    if post.owner_id != current_user.id and not current_user.is_moderator:
        raise HTTPException(
            status_code=403, detail="Not authorized to highlight this comment"
        )

    comment.is_highlighted = not comment.is_highlighted
    db.commit()
    return comment


@router.put("/{comment_id}/best-answer", response_model=schemas.CommentOut)
def set_best_answer(
    comment_id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(oauth2.get_current_user),
):
    comment = db.query(models.Comment).filter(models.Comment.id == comment_id).first()
    if not comment:
        raise HTTPException(status_code=404, detail="Comment not found")

    post = db.query(models.Post).filter(models.Post.id == comment.post_id).first()
    if post.owner_id != current_user.id:
        raise HTTPException(status_code=403, detail="Not authorized to set best answer")

    # Reset previous best answer if exists
    previous_best = (
        db.query(models.Comment)
        .filter(
            models.Comment.post_id == post.id, models.Comment.is_best_answer == True
        )
        .first()
    )
    if previous_best:
        previous_best.is_best_answer = False

    comment.is_best_answer = True
    post.has_best_answer = True
    db.commit()
    return comment
