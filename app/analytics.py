from sqlalchemy import func
from datetime import (
    datetime,
    timedelta,
    timezone,
)  # Added timezone for correct UTC usage
import logging
from . import models
from transformers import pipeline, AutoTokenizer, AutoModelForSequenceClassification
from .config import settings
import matplotlib.pyplot as plt
import seaborn as sns
import io
import base64
from .models import SearchStatistics, User
from sqlalchemy.orm import Session
from .utils import keyword_sentiment

# NOTE: Ensure that get_db() is defined in your project or import it accordingly.
# from .database import get_db

logger = logging.getLogger(__name__)

# Initialize the tokenizer and model for sentiment analysis with graceful fallback
try:
    tokenizer = AutoTokenizer.from_pretrained(
        "distilbert-base-uncased-finetuned-sst-2-english"
    )
    model = AutoModelForSequenceClassification.from_pretrained(
        "distilbert-base-uncased-finetuned-sst-2-english"
    )
    sentiment_pipeline = pipeline("sentiment-analysis", model=model, tokenizer=tokenizer)
except Exception as exc:  # pragma: no cover - defensive fallback
    logger.warning(
        "Analytics sentiment pipeline unavailable, using keyword heuristic: %s",
        exc,
    )
    tokenizer = model = None
    sentiment_pipeline = None

# ------------------------- Content Analysis Functions -------------------------


def analyze_sentiment(text):
    """
    Analyze the sentiment of the given text using a pre-trained transformer model.
    Returns a dictionary with sentiment label and score.
    """
    if sentiment_pipeline is not None:
        try:
            result = sentiment_pipeline(text)[0]
            return {"sentiment": result["label"], "score": float(result["score"])}
        except Exception as exc:  # pragma: no cover - defensive fallback
            logger.warning(
                "Analytics sentiment pipeline failed, using keyword heuristic: %s",
                exc,
            )
    label, score = keyword_sentiment(text)
    return {"sentiment": label, "score": score}


def suggest_improvements(text, sentiment):
    """
    Provide suggestions for improvements based on the sentiment analysis.
    If the sentiment is negative with high confidence or the text is too short,
    suggestions are provided to improve the post.
    """
    if sentiment["sentiment"] == "NEGATIVE" and sentiment["score"] > 0.8:
        return "Consider rephrasing your post to have a more positive tone."
    elif len(text.split()) < 10:
        return "Your post seems short. Consider adding more details to engage your audience."
    else:
        return "Your post looks good!"


def analyze_content(text):
    """
    Analyze the content of the text by determining its sentiment and suggesting improvements.
    """
    sentiment = analyze_sentiment(text)
    suggestion = suggest_improvements(text, sentiment)
    return {"sentiment": sentiment, "suggestion": suggestion}


# ------------------------- User Activity & Reporting Functions -------------------------


def get_user_activity(db: Session, user_id: int, days: int = 30):
    """
    Retrieve user activity events for the past 'days' days.
    Returns a dictionary with event types and their respective counts.
    """
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
    """
    Identify users with a number of valid reports greater than or equal to the threshold within the past 30 days.
    """
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
    """
    Get overall ban statistics including total bans and average ban duration.
    """
    return db.query(
        func.count(models.UserBan.id).label("total_bans"),
        func.avg(models.UserBan.duration).label("avg_duration"),
    ).first()


# ------------------------- Search Statistics Functions -------------------------


def record_search_query(db: Session, query: str, user_id: int):
    """
    Record a search query. If the query exists for the user, increment the count;
    otherwise, create a new record.
    """
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
    """
    Retrieve the most popular searches based on the count.
    """
    return (
        db.query(SearchStatistics)
        .order_by(SearchStatistics.count.desc())
        .limit(limit)
        .all()
    )


def get_recent_searches(db: Session, limit: int = 10):
    """
    Retrieve the most recent search queries.
    """
    return (
        db.query(SearchStatistics)
        .order_by(SearchStatistics.last_searched.desc())
        .limit(limit)
        .all()
    )


def get_user_searches(db: Session, user_id: int, limit: int = 10):
    """
    Retrieve recent search queries for a specific user.
    """
    return (
        db.query(SearchStatistics)
        .filter(SearchStatistics.user_id == user_id)
        .order_by(SearchStatistics.last_searched.desc())
        .limit(limit)
        .all()
    )


def clean_old_statistics(db: Session, days: int = 30):
    """
    Delete search statistics that are older than the specified number of days.
    """
    threshold = datetime.now() - timedelta(days=days)
    db.query(SearchStatistics).filter(
        SearchStatistics.last_searched < threshold
    ).delete()
    db.commit()


def generate_search_trends_chart():
    """
    Generate a line chart showing search trends over time.
    Returns the chart as a base64 encoded PNG image.
    """
    db = next(get_db())  # Ensure get_db() is properly defined in your project
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


# ------------------------- Conversation Statistics Function -------------------------


def update_conversation_statistics(
    db: Session, conversation_id: str, new_message: models.Message
):
    """
    Update conversation statistics based on a new message.
    - Increments total messages.
    - Updates the last message time.
    - Increments counters for attachments, emojis, and stickers.
    - Calculates response time based on the previous message.
    """
    stats = (
        db.query(models.ConversationStatistics)
        .filter(models.ConversationStatistics.conversation_id == conversation_id)
        .first()
    )

    # If no statistics exist for this conversation, create a new record.
    if not stats:
        stats = models.ConversationStatistics(
            conversation_id=conversation_id,
            user1_id=min(new_message.sender_id, new_message.receiver_id),
            user2_id=max(new_message.sender_id, new_message.receiver_id),
            total_messages=0,
            total_files=0,
            total_emojis=0,
            total_stickers=0,
            total_response_time=0,
            total_responses=0,
            average_response_time=0,
            last_message_at=None,
        )
        db.add(stats)

    # Update basic statistics
    stats.total_messages += 1
    stats.last_message_at = func.now()

    # Update counts for attachments, emojis, and stickers
    if new_message.attachments:
        stats.total_files += len(new_message.attachments)
    if new_message.has_emoji:
        stats.total_emojis += 1
    if hasattr(new_message, "message_type") and new_message.message_type == "sticker":
        stats.total_stickers += 1

    # Calculate response time if a previous message exists
    last_message = (
        db.query(models.Message)
        .filter(
            models.Message.conversation_id == conversation_id,
            models.Message.id != new_message.id,
        )
        .order_by(models.Message.created_at.desc())
        .first()
    )

    if last_message:
        time_diff = (new_message.created_at - last_message.created_at).total_seconds()
        stats.total_response_time += time_diff
        stats.total_responses += 1
        stats.average_response_time = stats.total_response_time / stats.total_responses

    db.commit()
