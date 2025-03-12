from fastapi import APIRouter, HTTPException, status, Depends, BackgroundTasks, Query
from sqlalchemy.orm import Session, joinedload
from sqlalchemy import desc, asc
from typing import List, Optional
from datetime import datetime, timedelta
import emoji
from app import models
from app.notifications import create_notification
from ..models import Comment, Post, User
from .. import schemas, oauth2
from ..database import get_db
from ..utils import (
    check_content_against_rules,
    check_for_profanity,
    validate_urls,
    log_user_event,
    analyze_sentiment,
    is_valid_image_url,
    is_valid_video_url,
    get_translated_content,
    detect_language,
    update_post_score,
)
from ..config import settings

router = APIRouter(prefix="/comments", tags=["Comments"])

# إذا لم يكن هناك حد زمني للتعديل، نترك EDIT_WINDOW فارغاً
EDIT_WINDOW = None


# Utility Functions
def check_comment_owner(comment: Comment, user: User):
    """
    Verify that the comment belongs to the given user.
    """
    if comment.owner_id != user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Not authorized to perform requested action",
        )


async def validate_comment_content(
    comment: schemas.CommentCreate,
    post: Post,
    db: Session,
):
    """
    Validate the comment content.

    Checks community rules, and validates image and video URLs.
    """
    if post.community_id:
        community_rules = [rule.rule for rule in post.community.rules]
        if not check_content_against_rules(comment.content, community_rules):
            raise HTTPException(
                status_code=400, detail="Comment content violates community rules"
            )

    if comment.image_url and not is_valid_image_url(comment.image_url):
        raise HTTPException(status_code=400, detail="Invalid image URL")

    if comment.video_url and not is_valid_video_url(comment.video_url):
        raise HTTPException(status_code=400, detail="Invalid video URL")


# API Endpoints


@router.post(
    "/", status_code=status.HTTP_201_CREATED, response_model=schemas.CommentOut
)
async def create_comment(
    background_tasks: BackgroundTasks,
    comment: schemas.CommentCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(oauth2.get_current_user),
):
    """
    Create a new comment.

    Parameters:
      - comment: CommentCreate schema containing comment data.
      - background_tasks: For scheduling background tasks.
      - db: Database session.
      - current_user: The authenticated user.

    Process:
      - Verify user is verified.
      - Verify that the post exists.
      - Validate the comment content.
      - Create a new comment and update related counts.
      - Log the event and send notifications.
      - Update the post score.

    Returns:
      The newly created comment.
    """
    if not current_user.is_verified:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="User is not verified."
        )

    post = db.query(Post).filter(Post.id == comment.post_id).first()
    if not post:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Post not found"
        )

    await validate_comment_content(comment, post, db)

    new_comment = Comment(
        owner_id=current_user.id,
        post_id=comment.post_id,
        parent_id=comment.parent_id,
        content=comment.content,
        image_url=comment.image_url,
        video_url=comment.video_url,
        has_emoji=emoji.emoji_count(comment.content) > 0,
        has_sticker=comment.sticker_id is not None,
        sticker_id=comment.sticker_id,
        language=detect_language(comment.content),
    )

    new_comment.contains_profanity = check_for_profanity(comment.content)
    new_comment.has_invalid_urls = not validate_urls(comment.content)
    new_comment.sentiment_score = analyze_sentiment(comment.content)

    current_user.comment_count += 1
    post.comment_count += 1

    db.add(new_comment)
    db.commit()
    db.refresh(new_comment)

    log_user_event(
        db,
        current_user.id,
        "create_comment",
        {"comment_id": new_comment.id, "post_id": comment.post_id},
    )

    create_notification(
        db,
        post.owner_id,
        f"{current_user.username} commented on your post",
        f"/post/{post.id}",
        "new_comment",
        new_comment.id,
    )

    if comment.parent_id:
        parent_comment = (
            db.query(Comment).filter(Comment.id == comment.parent_id).first()
        )
        if parent_comment and parent_comment.owner_id != post.owner_id:
            create_notification(
                db,
                parent_comment.owner_id,
                f"{current_user.username} replied to your comment",
                f"/post/{post.id}#comment-{new_comment.id}",
                "reply_to_comment",
                new_comment.id,
            )

    update_post_score(db, post)

    return new_comment


@router.get("/{post_id}", response_model=List[schemas.CommentOut])
async def get_comments(
    post_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(oauth2.get_current_user),
    sort_by: Optional[str] = Query("created_at", enum=["created_at", "likes_count"]),
    sort_order: Optional[str] = Query("desc", enum=["asc", "desc"]),
    skip: int = 0,
    limit: int = 100,
):
    """
    Retrieve comments for a post.

    Parameters:
      - post_id: ID of the post.
      - sort_by: Field to sort comments by.
      - sort_order: Sort order.
      - skip: Number of comments to skip.
      - limit: Maximum number of comments to return.

    Process:
      - Verify that the post exists.
      - Apply sorting.
      - Filter out flagged comments for non-moderators.
      - Translate comment content.

    Returns:
      A list of comments.
    """
    post = db.query(Post).filter(Post.id == post_id).first()
    if not post:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Post not found"
        )

    query = db.query(Comment).filter(
        Comment.post_id == post_id, Comment.parent_id == None
    )

    if sort_by == "created_at":
        query = query.order_by(
            desc(Comment.created_at)
            if sort_order == "desc"
            else asc(Comment.created_at)
        )
    elif sort_by == "likes_count":
        query = query.order_by(
            desc(Comment.likes_count)
            if sort_order == "desc"
            else asc(Comment.likes_count)
        )

    if not current_user.is_moderator:
        query = query.filter(Comment.is_flagged == False)

    comments = (
        query.options(joinedload(Comment.replies)).offset(skip).limit(limit).all()
    )
    for comment in comments:
        comment.content = await get_translated_content(
            comment.content, current_user, comment.language
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
    """
    Retrieve replies for a specific comment.

    Parameters:
      - comment_id: ID of the parent comment.
      - sort_by: Field to sort by.
      - sort_order: Sort order.

    Returns:
      A list of replies.
    """
    comment = db.query(Comment).filter(Comment.id == comment_id).first()
    if not comment:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Comment not found"
        )

    query = db.query(Comment).filter(Comment.parent_id == comment_id)

    if sort_by == "created_at":
        query = query.order_by(
            desc(Comment.created_at)
            if sort_order == "desc"
            else asc(Comment.created_at)
        )
    elif sort_by == "likes_count":
        query = query.order_by(
            desc(Comment.likes_count)
            if sort_order == "desc"
            else asc(Comment.likes_count)
        )

    if not current_user.is_moderator:
        query = query.filter(Comment.is_flagged == False)

    replies = query.all()
    return replies


@router.put("/{comment_id}", response_model=schemas.Comment)
def update_comment(
    comment_id: int,
    updated_comment: schemas.CommentUpdate,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(oauth2.get_current_user),
):
    """
    Update an existing comment.

    Parameters:
      - comment_id: ID of the comment to update.
      - updated_comment: New content for the comment.
      - db: Database session.
      - current_user: The authenticated user.

    Process:
      - Verify comment existence.
      - Check ownership and edit window.
      - Save previous content to edit history.
      - Update the comment and mark it as edited.

    Returns:
      The updated comment.
    """
    comment = db.query(Comment).filter(Comment.id == comment_id).first()
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
    """
    Soft delete a comment.

    Parameters:
      - comment_id: ID of the comment to delete.
      - db: Database session.
      - current_user: The authenticated user.

    Process:
      - Verify comment existence and ownership.
      - Mark the comment as deleted and update deletion timestamp.

    Returns:
      A confirmation message.
    """
    comment = db.query(Comment).filter(Comment.id == comment_id).first()
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
    """
    Retrieve the edit history for a specific comment.

    Parameters:
      - comment_id: ID of the comment.
      - db: Database session.
      - current_user: The authenticated user.

    Returns:
      A list of edit history records for the comment.

    Raises:
      HTTPException: If the comment is not found or if access is unauthorized.
    """
    comment = db.query(Comment).filter(Comment.id == comment_id).first()
    if not comment:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Comment not found"
        )

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
    """
    Report a post or comment.

    Parameters:
      - report: ReportCreate schema containing report details.
      - db: Database session.
      - current_user: The authenticated user.
      - background_tasks: For sending notifications asynchronously.

    Process:
      - Determine the reported content (post or comment).
      - Check content for profanity and invalid URLs.
      - Create a new report record.
      - Automatically flag the content if violations are found.
      - Notify moderators if necessary.

    Returns:
      The created report record.
    """
    if report.post_id:
        post = db.query(Post).filter(Post.id == report.post_id).first()
        if not post:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail="Post not found"
            )
        reported_content = post.content
        reported_type = "post"
    elif report.comment_id:
        comment = db.query(Comment).filter(Comment.id == report.comment_id).first()
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

    contains_profanity = check_for_profanity(reported_content)
    has_invalid_urls = not validate_urls(reported_content)

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

    if contains_profanity or has_invalid_urls:
        if reported_type == "post":
            post.is_flagged = True
            post.flag_reason = "Automatic content check"
        else:
            comment.is_flagged = True
            comment.flag_reason = "Automatic content check"
        db.commit()

        moderators = db.query(User).filter(User.role == "moderator").all()
        for moderator in moderators:
            background_tasks.add_task(
                send_email_notification,
                to=moderator.email,
                subject=f"New flagged {reported_type}",
                body=f"A {reported_type} has been automatically flagged. {reported_type.capitalize()} ID: {report.post_id or report.comment_id}",
            )

    return new_report


@router.post("/{comment_id}/flag", status_code=status.HTTP_200_OK)
def flag_comment(
    comment_id: int,
    flag_reason: schemas.FlagCommentRequest,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(oauth2.get_current_user),
):
    """
    Flag a comment manually.

    Parameters:
      - comment_id: ID of the comment to flag.
      - flag_reason: FlagCommentRequest schema with flag reason.
      - db: Database session.
      - current_user: The authenticated user.

    Returns:
      A confirmation message.
    """
    comment = db.query(Comment).filter(Comment.id == comment_id).first()
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
    """
    Like a comment.

    Parameters:
      - comment_id: ID of the comment to like.
      - db: Database session.
      - current_user: The authenticated user.

    Returns:
      A confirmation message.
    """
    comment = db.query(Comment).filter(Comment.id == comment_id).first()
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
    """
    Toggle the highlighted status of a comment.

    Parameters:
      - comment_id: ID of the comment to highlight.
      - db: Database session.
      - current_user: The authenticated user.

    Returns:
      The updated comment.
    """
    comment = db.query(Comment).filter(Comment.id == comment_id).first()
    if not comment:
        raise HTTPException(status_code=404, detail="Comment not found")

    post = db.query(Post).filter(Post.id == comment.post_id).first()
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
    """
    Set a comment as the best answer for a post.

    Parameters:
      - comment_id: ID of the comment to mark as best answer.
      - db: Database session.
      - current_user: The authenticated user.

    Returns:
      The updated comment.
    """
    comment = db.query(Comment).filter(Comment.id == comment_id).first()
    if not comment:
        raise HTTPException(status_code=404, detail="Comment not found")

    post = db.query(Post).filter(Post.id == comment.post_id).first()
    if post.owner_id != current_user.id:
        raise HTTPException(status_code=403, detail="Not authorized to set best answer")

    previous_best = (
        db.query(Comment)
        .filter(Comment.post_id == post.id, Comment.is_best_answer == True)
        .first()
    )
    if previous_best:
        previous_best.is_best_answer = False

    comment.is_best_answer = True
    post.has_best_answer = True
    db.commit()
    return comment


@router.put("/{comment_id}/pin", response_model=schemas.CommentOut)
def pin_comment(
    comment_id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(oauth2.get_current_user),
):
    """
    Pin or unpin a comment on a post.

    Parameters:
      - comment_id: ID of the comment to pin.
      - db: Database session.
      - current_user: The authenticated user.

    Returns:
      The updated comment.

    Raises:
      HTTPException: If maximum number of pinned comments is reached.
    """
    comment = db.query(Comment).filter(Comment.id == comment_id).first()
    if not comment:
        raise HTTPException(status_code=404, detail="Comment not found")

    post = db.query(Post).filter(Post.id == comment.post_id).first()
    if post.owner_id != current_user.id and not current_user.is_moderator:
        raise HTTPException(
            status_code=403, detail="Not authorized to pin this comment"
        )

    if comment.is_pinned:
        pinned_comments_count = (
            db.query(Comment)
            .filter(Comment.post_id == post.id, Comment.is_pinned == True)
            .count()
        )
        if pinned_comments_count >= post.max_pinned_comments:
            raise HTTPException(
                status_code=400,
                detail=f"Maximum number of pinned comments ({post.max_pinned_comments}) reached for this post",
            )

    comment.is_pinned = not comment.is_pinned
    comment.pinned_at = datetime.now(timezone.utc) if comment.is_pinned else None
    db.commit()
    db.refresh(comment)
    return comment
