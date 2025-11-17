"""Content moderation, sentiment, and repost helpers."""

from __future__ import annotations

import os
import re
from datetime import datetime, timezone
from typing import List, Tuple

import joblib
import validators
from better_profanity import profanity
from langdetect import detect, LangDetectException
from sklearn.feature_extraction.text import CountVectorizer
from sklearn.naive_bayes import MultinomialNB
from sqlalchemy import func
from sqlalchemy.orm import Session
from transformers import AutoModelForSequenceClassification, AutoTokenizer, pipeline

import nltk
from nltk.corpus import stopwords

from app import models
from app.core.config import settings
from .common import get_user_display_name, logger

nltk.download("stopwords", quiet=True)
profanity.load_censor_words()

model_name = "cardiffnlp/twitter-roberta-base-offensive"
offensive_classifier = pipeline(
    "text-classification",
    model=model_name,
    device=0 if getattr(settings, "USE_GPU", False) else -1,
)

tokenizer = AutoTokenizer.from_pretrained(
    "distilbert-base-uncased-finetuned-sst-2-english"
)
sentiment_model = AutoModelForSequenceClassification.from_pretrained(
    "distilbert-base-uncased-finetuned-sst-2-english"
)
sentiment_pipeline = pipeline(
    "sentiment-analysis", model=sentiment_model, tokenizer=tokenizer
)


def check_content_against_rules(content: str, rules: List[str]) -> bool:
    """Return False when content matches a disallowed rule."""
    for rule in rules:
        if re.search(rule, content, re.IGNORECASE):
            return False
    return True


def detect_language(text: str) -> str:
    """Detect the language of text; fall back to 'unknown'."""
    try:
        return detect(text)
    except LangDetectException:
        return "unknown"


def train_content_classifier():
    """Train a naïve Bayes classifier with placeholder data."""
    X = ["This is a good comment", "Bad comment with profanity", "Normal text here"]
    y = [0, 1, 0]
    vectorizer = CountVectorizer(stop_words=stopwords.words("english"))
    X_vectorized = vectorizer.fit_transform(X)
    classifier = MultinomialNB()
    classifier.fit(X_vectorized, y)
    joblib.dump(classifier, "content_classifier.joblib")
    joblib.dump(vectorizer, "content_vectorizer.joblib")


def check_for_profanity(text: str) -> bool:
    """Detect offensive text using profanity list and ML classifier."""
    if profanity.contains_profanity(text):
        return True
    if not os.path.exists("content_classifier.joblib"):
        train_content_classifier()
    classifier = joblib.load("content_classifier.joblib")
    vectorizer = joblib.load("content_vectorizer.joblib")
    X_vectorized = vectorizer.transform([text])
    prediction = classifier.predict(X_vectorized)
    return prediction[0] == 1


def validate_urls(text: str) -> bool:
    """Validate all URLs present in the text."""
    words = text.split()
    urls = [word for word in words if word.startswith(("http://", "https://"))]
    return all(validators.url(url) for url in urls)


def is_valid_image_url(url: str) -> bool:
    """Check if URL points to an image resource."""
    try:
        import requests

        response = requests.head(url)
        return response.headers.get("content-type", "").startswith("image/")
    except Exception:
        return False


def is_valid_video_url(url: str) -> bool:
    """Check if URL belongs to a supported video hosting service."""
    from urllib.parse import urlparse

    parsed_url = urlparse(url)
    video_hosts = ["youtube.com", "vimeo.com", "dailymotion.com"]
    return any(host in parsed_url.netloc for host in video_hosts)


def analyze_sentiment(text: str) -> float:
    """Analyze sentiment using TextBlob polarity score."""
    from textblob import TextBlob

    analysis = TextBlob(text)
    return analysis.sentiment.polarity


def process_mentions(content: str, db: Session):
    """Extract and return mentioned users."""
    mentioned_usernames = re.findall(r"@(\w+)", content)
    mentioned_users = []
    for username in mentioned_usernames:
        user = db.query(models.User).filter(models.User.username == username).first()
        if user:
            mentioned_users.append(user)
    return mentioned_users


def is_content_offensive(text: str) -> Tuple[bool, float]:
    """Detect offensive content using Hugging Face pipeline."""
    result = offensive_classifier(text)[0]
    is_offensive = result["label"] == "LABEL_1" and result["score"] > 0.8
    return is_offensive, result["score"]


def get_or_create_hashtag(db: Session, hashtag_name: str):
    """Retrieve or create a hashtag."""
    hashtag = (
        db.query(models.Hashtag).filter(models.Hashtag.name == hashtag_name).first()
    )
    if not hashtag:
        hashtag = models.Hashtag(name=hashtag_name)
        db.add(hashtag)
        db.commit()
        db.refresh(hashtag)
    return hashtag


def update_repost_statistics(db: Session, post_id: int):
    """Update repost statistics for a specific post."""
    stats = (
        db.query(models.RepostStatistics)
        .filter(models.RepostStatistics.post_id == post_id)
        .first()
    )
    if not stats:
        stats = models.RepostStatistics(post_id=post_id)
        db.add(stats)
    stats.repost_count += 1
    stats.last_reposted = datetime.now(timezone.utc)
    db.commit()


def send_repost_notification(
    db: Session, original_owner_id: int, reposter_id: int, repost_id: int
):
    """Send a notification when a post is reposted."""
    original_owner = (
        db.query(models.User).filter(models.User.id == original_owner_id).first()
    )
    reposter = db.query(models.User).filter(models.User.id == reposter_id).first()
    if not original_owner or not reposter:
        return
    notification = models.Notification(
        user_id=original_owner_id,
        content=f"{get_user_display_name(reposter)} has reposted your post",
        link=f"/post/{repost_id}",
        notification_type="repost",
    )
    db.add(notification)
    db.commit()


__all__ = [
    "sentiment_pipeline",
    "check_content_against_rules",
    "detect_language",
    "train_content_classifier",
    "check_for_profanity",
    "validate_urls",
    "is_valid_image_url",
    "is_valid_video_url",
    "analyze_sentiment",
    "process_mentions",
    "is_content_offensive",
    "get_or_create_hashtag",
    "update_repost_statistics",
    "send_repost_notification",
]
