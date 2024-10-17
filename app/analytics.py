from sqlalchemy import func
from datetime import datetime, timedelta
from . import models
from transformers import pipeline, AutoTokenizer, AutoModelForSequenceClassification
import torch
from .config import settings


# تهيئة النموذج والتوكنايزر
tokenizer = AutoTokenizer.from_pretrained(
    "distilbert-base-uncased-finetuned-sst-2-english"
)
model = AutoModelForSequenceClassification.from_pretrained(
    "distilbert-base-uncased-finetuned-sst-2-english"
)

sentiment_pipeline = pipeline("sentiment-analysis", model=model, tokenizer=tokenizer)


def analyze_sentiment(text):
    result = sentiment_pipeline(text)[0]
    return {"sentiment": result["label"], "score": result["score"]}


def suggest_improvements(text, sentiment):
    if sentiment["sentiment"] == "NEGATIVE" and sentiment["score"] > 0.8:
        return "Consider rephrasing your post to have a more positive tone."
    elif len(text.split()) < 10:
        return "Your post seems short. Consider adding more details to engage your audience."
    else:
        return "Your post looks good!"


def analyze_content(text):
    sentiment = analyze_sentiment(text)
    suggestion = suggest_improvements(text, sentiment)
    return {"sentiment": sentiment, "suggestion": suggestion}


def get_user_activity(db: Session, user_id: int, days: int = 30):
    end_date = datetime.now(timezone.utc)
    start_date = end_date - timedelta(days=days)

    activities = (
        db.query(
            models.UserEvent.event_type, func.count(models.UserEvent.id).label("count")
        )
        .filter(
            models.UserEvent.user_id == user_id,
            models.UserEvent.created_at.between(start_date, end_date),
        )
        .group_by(models.UserEvent.event_type)
        .all()
    )

    return {activity.event_type: activity.count for activity in activities}


def get_problematic_users(db: Session, threshold: int = 5):
    subquery = (
        db.query(
            models.Report.reported_user_id,
            func.count(models.Report.id).label("report_count"),
        )
        .filter(
            models.Report.is_valid == True,
            models.Report.created_at >= datetime.now(timezone.utc) - timedelta(days=30),
        )
        .group_by(models.Report.reported_user_id)
        .subquery()
    )

    return (
        db.query(models.User)
        .join(subquery, models.User.id == subquery.c.reported_user_id)
        .filter(subquery.c.report_count >= threshold)
        .all()
    )


def get_ban_statistics(db: Session):
    return db.query(
        func.count(models.UserBan.id).label("total_bans"),
        func.avg(models.UserBan.duration).label("avg_duration"),
    ).first()
