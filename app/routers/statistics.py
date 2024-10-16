from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from sqlalchemy import func
from .. import models, schemas, oauth2
from ..database import get_db

router = APIRouter(prefix="/statistics", tags=["Statistics"])


@router.get("/comments", response_model=schemas.CommentStatistics)
async def get_comment_statistics(db: Session = Depends(get_db)):
    total_comments = db.query(func.count(models.Comment.id)).scalar()
    top_commenters = (
        db.query(
            models.User.id,
            models.User.username,
            func.count(models.Comment.id).label("comment_count"),
        )
        .join(models.Comment)
        .group_by(models.User.id)
        .order_by(func.count(models.Comment.id).desc())
        .limit(5)
        .all()
    )

    most_commented_posts = (
        db.query(
            models.Post.id,
            models.Post.title,
            func.count(models.Comment.id).label("comment_count"),
        )
        .join(models.Comment)
        .group_by(models.Post.id)
        .order_by(func.count(models.Comment.id).desc())
        .limit(5)
        .all()
    )

    avg_sentiment = db.query(func.avg(models.Comment.sentiment_score)).scalar()

    return {
        "total_comments": total_comments,
        "top_commenters": top_commenters,
        "most_commented_posts": most_commented_posts,
        "average_sentiment": avg_sentiment,
    }
