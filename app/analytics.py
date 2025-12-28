from sqlalchemy import func
from datetime import (
    datetime,
    timedelta,
    timezone,
)  # Added timezone for correct UTC usage
from . import models
from transformers import pipeline, AutoTokenizer, AutoModelForSequenceClassification
from app.core.database import get_db
import matplotlib.pyplot as plt
import seaborn as sns
import io
import base64
import polars as pl
from .models import SearchStatistics
from app.modules.users.models import User, UserEvent
from app.modules.search import SearchStatOut
from app.modules.search.cache import (
    get_cached_json,
    invalidate_stats_cache,
    popular_cache_key,
    recent_cache_key,
    set_cached_json,
    user_cache_key,
)
from sqlalchemy.orm import Session
import logging

_PIPELINE_NAME = "distilbert-base-uncased-finetuned-sst-2-english"
_sentiment_pipeline = None
model = None

_STAT_QUERY_ATTR = "query" if hasattr(SearchStatistics, "query") else "term"
_STAT_COUNT_ATTR = "count" if hasattr(SearchStatistics, "count") else "searches"
_STAT_TS_ATTR = (
    "last_searched"
    if hasattr(SearchStatistics, "last_searched")
    else "updated_at"
)

logger = logging.getLogger(__name__)


def log_analysis_event(success: bool, context: dict | None = None, error: Exception | str | None = None) -> None:
    """
    Lightweight logging helper for analytics operations.
    Never raises even if context is missing or malformed.
    """
    payload = context.copy() if isinstance(context, dict) else {}
    try:
        if success:
            logger.info("analytics.success", extra=payload or None)
        else:
            if error is not None:
                payload["error"] = str(error)
            logger.error("analytics.failure", extra=payload or None)
    except Exception:  # pragma: no cover - defensive guard
        logger.exception("analytics.log_failure_guard")


def merge_stats(base: dict | None, incoming: dict | None) -> dict:
    """
    Merge two stats dictionaries, summing numeric values when keys collide.
    Handles None inputs gracefully.
    """
    base = base or {}
    incoming = incoming or {}
    merged = dict(base)
    for key, value in incoming.items():
        if isinstance(value, (int, float)) and isinstance(merged.get(key), (int, float)):
            merged[key] = merged[key] + value  # type: ignore[index]
        else:
            merged[key] = value
    return merged


def _get_sentiment_pipeline():
    global _sentiment_pipeline, model
    if _sentiment_pipeline is None:
        tokenizer = AutoTokenizer.from_pretrained(_PIPELINE_NAME)
        model = AutoModelForSequenceClassification.from_pretrained(_PIPELINE_NAME)
        _sentiment_pipeline = pipeline(
            "sentiment-analysis", model=model, tokenizer=tokenizer
        )
    return _sentiment_pipeline

# ------------------------- Content Analysis Functions -------------------------


def analyze_sentiment(text):
    """
    Analyze the sentiment of the given text using a pre-trained transformer model.
    Returns a dictionary with sentiment label and score.
    """
    pipeline_instance = _get_sentiment_pipeline()
    result = pipeline_instance(text)[0]
    return {"sentiment": result["label"], "score": result["score"]}


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
        db.query(UserEvent.event_type, func.count(UserEvent.id).label("count"))
        .filter(
            UserEvent.user_id == user_id,
            UserEvent.created_at.between(start_date, end_date),
        )
        .group_by(UserEvent.event_type)
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
            models.Report.is_valid,
            models.Report.created_at
            >= datetime.now(timezone.utc) - timedelta(days=30),
        )
        .group_by(models.Report.reported_user_id)
        .subquery()
    )

    return (
        db.query(User)
        .join(subquery, User.id == subquery.c.reported_user_id)
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


def _schemas_from_rows(rows):
    stats = []
    for row in rows:
        stats.append(
            SearchStatOut(
                query=getattr(row, _STAT_QUERY_ATTR),
                count=getattr(row, _STAT_COUNT_ATTR),
                last_searched=getattr(row, _STAT_TS_ATTR),
            )
        )
    return stats


def _cache_stats(key: str, stats):
    set_cached_json(key, [stat.model_dump() for stat in stats], ttl_seconds=300)


def _cached_stats(key: str):
    payload = get_cached_json(key)
    if payload is None:
        return None
    return [SearchStatOut.model_validate(item) for item in payload]


def record_search_query(db: Session, query: str, user_id: int):
    """
    Record a search query. If the query exists for the user, increment the count;
    otherwise, create a new record.
    """
    query_column = getattr(SearchStatistics, _STAT_QUERY_ATTR)
    search_stat = (
        db.query(SearchStatistics)
        .filter(query_column == query, SearchStatistics.user_id == user_id)
        .first()
    )
    if search_stat:
        setattr(search_stat, _STAT_COUNT_ATTR, getattr(search_stat, _STAT_COUNT_ATTR) + 1)
        setattr(search_stat, _STAT_TS_ATTR, datetime.now(timezone.utc))
    else:
        search_stat = SearchStatistics(user_id=user_id, **{_STAT_QUERY_ATTR: query})
        setattr(search_stat, _STAT_COUNT_ATTR, 1)
        db.add(search_stat)
    db.commit()
    invalidate_stats_cache(for_user_id=user_id)


def get_popular_searches(db: Session, limit: int = 10):
    """
    Retrieve the most popular searches based on the count.
    """
    cache_key = popular_cache_key(limit)
    cached = _cached_stats(cache_key)
    if cached is not None:
        return cached
    rows = (
        db.query(SearchStatistics)
        .order_by(getattr(SearchStatistics, _STAT_COUNT_ATTR).desc())
        .limit(limit)
        .all()
    )
    stats = _schemas_from_rows(rows)
    _cache_stats(cache_key, stats)
    return stats


def get_recent_searches(db: Session, limit: int = 10):
    """
    Retrieve the most recent search queries.
    """
    cache_key = recent_cache_key(limit)
    cached = _cached_stats(cache_key)
    if cached is not None:
        return cached
    rows = (
        db.query(SearchStatistics)
        .order_by(getattr(SearchStatistics, _STAT_TS_ATTR).desc())
        .limit(limit)
        .all()
    )
    stats = _schemas_from_rows(rows)
    _cache_stats(cache_key, stats)
    return stats


def get_user_searches(db: Session, user_id: int, limit: int = 10):
    """
    Retrieve recent search queries for a specific user.
    """
    cache_key = user_cache_key(user_id, limit)
    cached = _cached_stats(cache_key)
    if cached is not None:
        return cached
    rows = (
        db.query(SearchStatistics)
        .filter(SearchStatistics.user_id == user_id)
        .order_by(getattr(SearchStatistics, _STAT_TS_ATTR).desc())
        .limit(limit)
        .all()
    )
    stats = _schemas_from_rows(rows)
    _cache_stats(cache_key, stats)
    return stats


def clean_old_statistics(db: Session, days: int = 30):
    """
    Delete search statistics that are older than the specified number of days.
    """
    threshold = datetime.now() - timedelta(days=days)
    timestamp_column = getattr(SearchStatistics, _STAT_TS_ATTR)
    db.query(SearchStatistics).filter(timestamp_column < threshold).delete()
    db.commit()


def generate_search_trends_chart():
    """
    Generate a line chart showing search trends over time using polars for aggregation.
    Returns the chart as a base64 encoded PNG image.
    """
    db = next(get_db())
    rows = (
        db.query(
            func.date(getattr(SearchStatistics, _STAT_TS_ATTR)).label("date"),
            func.count(SearchStatistics.id).label("count"),
        )
        .group_by(func.date(SearchStatistics.last_searched))
        .order_by("date")
        .all()
    )

    if not rows:
        return ""

    df = pl.DataFrame({"date": [r.date for r in rows], "count": [r.count for r in rows]})
    df = df.sort("date")

    plt.figure(figsize=(12, 6))
    sns.lineplot(x=df["date"].to_list(), y=df["count"].to_list())
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


def polars_merge_stats(stats_a: dict | None, stats_b: dict | None) -> dict:
    """
    Merge two stats dictionaries using polars for fast aggregation of numeric fields.
    """
    stats_a = stats_a or {}
    stats_b = stats_b or {}
    if not stats_a:
        return stats_b
    if not stats_b:
        return stats_a
    df = pl.DataFrame(
        {
            "key": list(stats_a.keys()) + list(stats_b.keys()),
            "value": list(stats_a.values()) + list(stats_b.values()),
        }
    )
    agg = df.group_by("key").agg(pl.col("value").sum()).to_dict(False)
    merged = dict(zip(agg["key"], agg["value"]))
    return merged


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
        receiver_id = new_message.receiver_id or new_message.sender_id
        stats = models.ConversationStatistics(
            conversation_id=conversation_id,
            user1_id=min(new_message.sender_id, receiver_id),
            user2_id=max(new_message.sender_id, receiver_id),
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
        .order_by(models.Message.timestamp.desc())
        .first()
    )

    if last_message:
        time_diff = (new_message.timestamp - last_message.timestamp).total_seconds()
        stats.total_response_time += time_diff
        stats.total_responses += 1
        stats.average_response_time = stats.total_response_time / stats.total_responses

    db.commit()
