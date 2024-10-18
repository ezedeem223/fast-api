from sqlalchemy import func
from datetime import datetime, timedelta
from . import models
from transformers import pipeline, AutoTokenizer, AutoModelForSequenceClassification
import torch
from .config import settings
import matplotlib.pyplot as plt
import seaborn as sns
import io
import base64
from .models import SearchStatistics, User
from sqlalchemy.orm import Session


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


def record_search_query(db: Session, query: str, user_id: int):
    search_stat = (
        db.query(SearchStatistics)
        .filter(SearchStatistics.query == query, SearchStatistics.user_id == user_id)
        .first()
    )
    if search_stat:
        search_stat.count += 1
    else:
        search_stat = SearchStatistics(query=query, user_id=user_id)
        db.add(search_stat)
    db.commit()


def get_popular_searches(db: Session, limit: int = 10):
    return (
        db.query(SearchStatistics)
        .order_by(SearchStatistics.count.desc())
        .limit(limit)
        .all()
    )


def get_recent_searches(db: Session, limit: int = 10):
    return (
        db.query(SearchStatistics)
        .order_by(SearchStatistics.last_searched.desc())
        .limit(limit)
        .all()
    )


def get_user_searches(db: Session, user_id: int, limit: int = 10):
    return (
        db.query(SearchStatistics)
        .filter(SearchStatistics.user_id == user_id)
        .order_by(SearchStatistics.last_searched.desc())
        .limit(limit)
        .all()
    )


def clean_old_statistics(db: Session, days: int = 30):
    threshold = datetime.now() - timedelta(days=days)
    db.query(SearchStatistics).filter(
        SearchStatistics.last_searched < threshold
    ).delete()
    db.commit()


def generate_search_trends_chart():
    db = next(get_db())
    data = (
        db.query(
            func.date(SearchStatistics.last_searched).label("date"),
            func.count(SearchStatistics.id).label("count"),
        )
        .group_by(func.date(SearchStatistics.last_searched))
        .order_by("date")
        .all()
    )

    dates = [row.date for row in data]
    counts = [row.count for row in data]

    plt.figure(figsize=(12, 6))
    sns.lineplot(x=dates, y=counts)
    plt.title("Search Trends Over Time")
    plt.xlabel("Date")
    plt.ylabel("Number of Searches")
    plt.xticks(rotation=45)
    plt.tight_layout()

    buffer = io.BytesIO()
    plt.savefig(buffer, format="png")
    buffer.seek(0)
    image_png = buffer.getvalue()
    buffer.close()

    graphic = base64.b64encode(image_png)
    graphic = graphic.decode("utf-8")

    return graphic
