"""
File: utils.py
Description: A comprehensive utility module that provides functions for authentication,
content moderation, file uploads, search, analytics, translation, and more.
Note: External functions such as 'translate_text' must be implemented in their respective modules.
It is recommended to refactor this file in the future into smaller modules according to the
Single Responsibility Principle.
"""

# ============================================
# Imports and Dependencies
# ============================================
from passlib.context import CryptContext
import re
import qrcode
import base64
from io import BytesIO
import os
from fastapi import UploadFile, Request, HTTPException, status
import aiofiles
from better_profanity import profanity
import validators
from sklearn.feature_extraction.text import CountVectorizer
from sklearn.naive_bayes import MultinomialNB
import nltk
from nltk.corpus import stopwords
import joblib
from functools import wraps, lru_cache
from cachetools import TTLCache
from sqlalchemy.orm import Session
from sqlalchemy import func, text, desc, asc, or_
from . import models, schemas
from transformers import pipeline, AutoTokenizer, AutoModelForSequenceClassification
from .config import settings
import secrets
from cryptography.fernet import Fernet
import time
from collections import deque
from datetime import datetime, timezone, date
from typing import List, Optional

# SpellChecker and language detection
from spellchecker import SpellChecker
import ipaddress
from langdetect import detect, LangDetectException

# Import external function for link preview extraction
from .link_preview import extract_link_preview

# Attempt to import 'translate_text' from an external module.
try:
    from .translation import translate_text
except ImportError:
    # Placeholder implementation; should be replaced with a proper implementation.
    async def translate_text(text: str, source_lang: str, target_lang: str):
        raise NotImplementedError("translate_text function is not implemented.")


# ============================================
# Global Variables and Constants
# ============================================
spell = SpellChecker()
translation_cache = TTLCache(maxsize=1000, ttl=3600)
cache = TTLCache(maxsize=100, ttl=60)  # Cache for temporary storage

QUALITY_WINDOW_SIZE = 10
MIN_QUALITY_THRESHOLD = 50

# Offensive content classifier initialization using Hugging Face model
model_name = "cardiffnlp/twitter-roberta-base-offensive"
offensive_classifier = pipeline(
    "text-classification",
    model=model_name,
    device=0 if getattr(settings, "USE_GPU", False) else -1,
)

# Password hashing configuration using bcrypt
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
nltk.download("stopwords", quiet=True)
profanity.load_censor_words()
tokenizer = AutoTokenizer.from_pretrained(
    "distilbert-base-uncased-finetuned-sst-2-english"
)
model = AutoModelForSequenceClassification.from_pretrained(
    "distilbert-base-uncased-finetuned-sst-2-english"
)
sentiment_pipeline = pipeline("sentiment-analysis", model=model, tokenizer=tokenizer)


# ============================================
# Authentication Utilities
# ============================================
def hash(password: str) -> str:
    """
    Encrypts the password using bcrypt.
    """
    return pwd_context.hash(password)


def verify(plain_password: str, hashed_password: str) -> bool:
    """
    Verifies a plain password against its hashed version.
    """
    return pwd_context.verify(plain_password, hashed_password)


# ============================================
# Content Moderation and Validation Functions
# ============================================
def check_content_against_rules(content: str, rules: List[str]) -> bool:
    """
    Checks if the content violates any of the regex-based rules.
    """
    for rule in rules:
        if re.search(rule, content, re.IGNORECASE):
            return False
    return True


def detect_language(text: str) -> str:
    """
    Detects the language of the given text.
    Returns 'unknown' if detection fails.
    """
    try:
        return detect(text)
    except LangDetectException:
        return "unknown"


def train_content_classifier():
    """
    Trains a simple content classifier using dummy data.
    Note: Replace dummy data with real data in production.
    """
    X = ["This is a good comment", "Bad comment with profanity", "Normal text here"]
    y = [0, 1, 0]  # 0: Normal content, 1: Offensive content

    vectorizer = CountVectorizer(stop_words=stopwords.words("english"))
    X_vectorized = vectorizer.fit_transform(X)

    classifier = MultinomialNB()
    classifier.fit(X_vectorized, y)

    # Save the classifier and the vectorizer for later use
    joblib.dump(classifier, "content_classifier.joblib")
    joblib.dump(vectorizer, "content_vectorizer.joblib")


def check_for_profanity(text: str) -> bool:
    """
    Checks if the text contains offensive words using better-profanity and a machine learning model.
    Returns True if offensive content is detected.
    """
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
    """
    Validates all URLs present in the text.
    Returns True if all URLs are valid.
    """
    words = text.split()
    urls = [word for word in words if word.startswith(("http://", "https://"))]
    return all(validators.url(url) for url in urls)


def is_valid_image_url(url: str) -> bool:
    """
    Checks if the URL points to an image resource.
    """
    try:
        import requests

        response = requests.head(url)
        return response.headers.get("content-type", "").startswith("image/")
    except Exception:
        return False


def is_valid_video_url(url: str) -> bool:
    """
    Checks if the URL belongs to a supported video hosting service.
    """
    from urllib.parse import urlparse

    parsed_url = urlparse(url)
    video_hosts = ["youtube.com", "vimeo.com", "dailymotion.com"]
    return any(host in parsed_url.netloc for host in video_hosts)


def analyze_sentiment(text: str) -> float:
    """
    Analyzes the sentiment of the text using TextBlob.
    Returns the polarity score.
    """
    from textblob import TextBlob

    analysis = TextBlob(text)
    return analysis.sentiment.polarity


# ============================================
# QR Code and File Upload Functions
# ============================================
def generate_qr_code(data: str) -> str:
    """
    Generates a QR code for the given data and returns it as a base64-encoded PNG string.
    """
    qr = qrcode.QRCode(version=1, box_size=10, border=5)
    qr.add_data(data)
    qr.make(fit=True)
    img = qr.make_image(fill_color="black", back_color="white")
    buffered = BytesIO()
    img.save(buffered, format="PNG")
    return base64.b64encode(buffered.getvalue()).decode()


async def save_upload_file(upload_file: UploadFile) -> str:
    """
    Asynchronously saves an uploaded file and returns its storage path.
    """
    file_location = f"uploads/{upload_file.filename}"
    async with aiofiles.open(file_location, "wb") as out_file:
        content = await upload_file.read()
        await out_file.write(content)
    return file_location


# ============================================
# Default Categories and Statistics Functions
# ============================================
def create_default_categories(db: Session):
    """
    Creates default post categories and subcategories if they do not already exist.
    """
    default_categories = [
        {"name": "Work", "description": "Posts related to job opportunities"},
        {
            "name": "Migration",
            "description": "Information and experiences about migration",
        },
        {"name": "Asylum", "description": "Posts regarding asylum procedures"},
    ]
    for category in default_categories:
        db_category = (
            db.query(models.PostCategory)
            .filter(models.PostCategory.name == category["name"])
            .first()
        )
        if not db_category:
            new_category = models.PostCategory(**category)
            db.add(new_category)
            db.commit()
            db.refresh(new_category)

            # Adding subcategories based on category
            if category["name"] == "Work":
                sub_categories = ["Work in Canada", "Work in USA", "Work in Europe"]
            elif category["name"] == "Migration":
                sub_categories = [
                    "Migration to Canada",
                    "Migration to USA",
                    "Migration to Australia",
                ]
            elif category["name"] == "Asylum":
                sub_categories = [
                    "Asylum in Europe",
                    "Asylum in Canada",
                    "Asylum in USA",
                ]

            for sub_cat in sub_categories:
                db_sub_category = (
                    db.query(models.PostCategory)
                    .filter(models.PostCategory.name == sub_cat)
                    .first()
                )
                if not db_sub_category:
                    new_sub_category = models.PostCategory(
                        name=sub_cat, parent_id=new_category.id
                    )
                    db.add(new_sub_category)
    db.commit()


def update_user_statistics(db: Session, user_id: int, action: str):
    """
    Updates user statistics in the database based on the action performed (post, comment, like, view).
    """
    today = date.today()
    stats = (
        db.query(models.UserStatistics)
        .filter(
            models.UserStatistics.user_id == user_id,
            models.UserStatistics.date == today,
        )
        .first()
    )
    if not stats:
        stats = models.UserStatistics(user_id=user_id, date=today)
        db.add(stats)

    if action == "post":
        stats.post_count += 1
    elif action == "comment":
        stats.comment_count += 1
    elif action == "like":
        stats.like_count += 1
    elif action == "view":
        stats.view_count += 1

    db.commit()


# ============================================
# IP Management and Ban Functions
# ============================================
def get_client_ip(request: Request) -> str:
    """
    Retrieves the client's IP address from the request headers.
    """
    forwarded_for = request.headers.get("X-Forwarded-For")
    if forwarded_for:
        return forwarded_for.split(",")[0].strip()
    return request.client.host


def is_ip_banned(db: Session, ip_address: str) -> bool:
    """
    Checks if the given IP address is banned.
    If the ban has expired, it removes the ban.
    """
    ban = db.query(models.IPBan).filter(models.IPBan.ip_address == ip_address).first()
    if ban:
        if ban.expires_at and ban.expires_at < datetime.now():
            db.delete(ban)
            db.commit()
            return False
        return True
    return False


def detect_ip_evasion(db: Session, user_id: int, current_ip: str) -> bool:
    """
    Detects if a user is using multiple IP addresses as an evasion tactic.
    Compares the current IP with the user's previous session IPs.
    """
    user_ips = (
        db.query(models.UserSession.ip_address)
        .filter(models.UserSession.user_id == user_id)
        .distinct()
        .all()
    )
    user_ips = [ip[0] for ip in user_ips]
    for ip in user_ips:
        if ip != current_ip and (
            ipaddress.ip_address(ip).is_private
            != ipaddress.ip_address(current_ip).is_private
        ):
            return True
    return False


# ============================================
# Hashtag and Repost Functions
# ============================================
def get_or_create_hashtag(db: Session, hashtag_name: str):
    """
    Retrieves an existing hashtag or creates a new one.
    """
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
    """
    Updates repost statistics for a specific post.
    """
    stats = (
        db.query(models.RepostStatistics)
        .filter(models.RepostStatistics.post_id == post_id)
        .first()
    )
    if not stats:
        stats = models.RepostStatistics(post_id=post_id)
        db.add(stats)
    stats.repost_count += 1
    stats.last_reposted = func.now()
    db.commit()


def send_repost_notification(
    db: Session, original_owner_id: int, reposter_id: int, repost_id: int
):
    """
    Sends a notification when a post is reposted.
    """
    original_owner = (
        db.query(models.User).filter(models.User.id == original_owner_id).first()
    )
    reposter = db.query(models.User).filter(models.User.id == reposter_id).first()
    notification = models.Notification(
        user_id=original_owner_id,
        content=f"{reposter.username} has reposted your post",
        link=f"/post/{repost_id}",
        notification_type="repost",
    )
    db.add(notification)
    db.commit()


# ============================================
# Mentions and Offensive Content Functions
# ============================================
def process_mentions(content: str, db: Session):
    """
    Extracts and processes user mentions from the content.
    """
    mentioned_usernames = re.findall(r"@(\w+)", content)
    mentioned_users = []
    for username in mentioned_usernames:
        user = db.query(models.User).filter(models.User.username == username).first()
        if user:
            mentioned_users.append(user)
    return mentioned_users


def is_content_offensive(text: str) -> tuple:
    """
    Determines if the text is offensive using an AI model.
    Returns a tuple (is_offensive, score) where is_offensive is a boolean.
    """
    result = offensive_classifier(text)[0]
    is_offensive = result["label"] == "LABEL_1" and result["score"] > 0.8
    return is_offensive, result["score"]


# ============================================
# Encryption Key Functions
# ============================================
def generate_encryption_key() -> str:
    """
    Generates a new encryption key using Fernet.
    """
    return Fernet.generate_key().decode()


def update_encryption_key(old_key: str) -> str:
    """
    Updates the encryption key.
    Note: Add logic for re-encrypting data if necessary.
    Returns the new key.
    """
    new_key = Fernet.generate_key()
    old_fernet = Fernet(old_key.encode())
    new_fernet = Fernet(new_key)
    return new_key.decode()


# ============================================
# Call Quality and Video Adjustment Functions
# ============================================
class CallQualityBuffer:
    """
    A class to store call quality scores within a specified time window.
    """

    def __init__(self, window_size=QUALITY_WINDOW_SIZE):
        self.window_size = window_size
        self.quality_scores = deque(maxlen=window_size)
        self.last_update_time = time.time()

    def add_score(self, score: float):
        """
        Adds a new score to the quality buffer.
        """
        self.quality_scores.append(score)
        self.last_update_time = time.time()

    def get_average_score(self) -> float:
        """
        Computes the average quality score.
        """
        if not self.quality_scores:
            return 100.0  # Assume excellent quality if no scores are recorded
        return sum(self.quality_scores) / len(self.quality_scores)


quality_buffers = {}


def check_call_quality(data: dict, call_id: str) -> float:
    """
    Calculates the call quality score based on packet loss, latency, and jitter.
    Returns the average quality score.
    """
    packet_loss = data.get("packet_loss", 0)
    latency = data.get("latency", 0)
    jitter = data.get("jitter", 0)
    quality_score = 100 - (packet_loss * 2 + latency / 10 + jitter)
    if call_id not in quality_buffers:
        quality_buffers[call_id] = CallQualityBuffer()
    quality_buffers[call_id].add_score(quality_score)
    return quality_buffers[call_id].get_average_score()


def should_adjust_video_quality(call_id: str) -> bool:
    """
    Determines if video quality should be adjusted based on the average score.
    """
    if call_id in quality_buffers:
        average_quality = quality_buffers[call_id].get_average_score()
        return average_quality < MIN_QUALITY_THRESHOLD
    return False


def get_recommended_video_quality(call_id: str) -> str:
    """
    Recommends the video quality level based on the average quality score.
    """
    if call_id in quality_buffers:
        average_quality = quality_buffers[call_id].get_average_score()
        if average_quality < 30:
            return "low"
        elif average_quality < 60:
            return "medium"
        else:
            return "high"
    return "high"  # Default quality if no data is available


def clean_old_quality_buffers():
    """
    Removes call quality buffers that have not been updated for more than 5 minutes.
    """
    current_time = time.time()
    for call_id in list(quality_buffers.keys()):
        if current_time - quality_buffers[call_id].last_update_time > 300:
            del quality_buffers[call_id]


# ============================================
# Search and Spellcheck Functions
# ============================================
def update_search_vector():
    """
    Updates the full-text search vector for posts in the database.
    Note: Ensure the database engine is correctly configured.
    """
    from sqlalchemy import create_engine

    engine = create_engine(settings.DATABASE_URL)
    with engine.connect() as conn:
        conn.execute(
            text(
                """
                UPDATE posts
                SET search_vector = to_tsvector('english', 
                    coalesce(title,'') || ' ' || 
                    coalesce(content,'') || ' ' || 
                    coalesce(media_text,''))
                """
            )
        )


def search_posts(query: str, db: Session):
    """
    Searches for posts matching the given query using full-text search.
    """
    search_query = func.plainto_tsquery("english", query)
    return (
        db.query(models.Post)
        .filter(
            or_(
                models.Post.search_vector.op("@@")(search_query),
                models.Post.media_text.ilike(f"%{query}%"),
            )
        )
        .all()
    )


def get_spell_suggestions(query: str) -> List[str]:
    """
    Generates spelling suggestions for the given query.
    """
    words = query.split()
    suggestions = []
    for word in words:
        if word not in spell:
            suggestions.append(spell.correction(word))
        else:
            suggestions.append(word)
    return suggestions


def format_spell_suggestions(original_query: str, suggestions: List[str]) -> str:
    """
    Formats the spelling suggestions if the corrected query differs from the original.
    """
    if original_query.lower() != " ".join(suggestions).lower():
        return f"Did you mean: {' '.join(suggestions)}?"
    return ""


def sort_search_results(query, sort_option: str, db: Session):
    """
    Sorts search results based on relevance, date, or popularity.
    """
    if sort_option == "RELEVANCE":
        return query.order_by(
            desc(
                func.ts_rank(
                    models.Post.search_vector, func.plainto_tsquery("english", query)
                )
            )
        )
    elif sort_option == "DATE_DESC":
        return query.order_by(desc(models.Post.created_at))
    elif sort_option == "DATE_ASC":
        return query.order_by(asc(models.Post.created_at))
    elif sort_option == "POPULARITY":
        return query.order_by(desc(models.Post.votes))
    else:
        return query


# ============================================
# User Behavior and Post Scoring Functions
# ============================================
def analyze_user_behavior(user_history, content: str) -> float:
    """
    Analyzes user behavior based on search history and the sentiment of the content.
    Returns a relevance score.
    """
    user_interests = set(item.lower() for item in user_history)
    result = sentiment_pipeline(content[:512])[0]  # Limit text length for analysis
    sentiment = result["label"]
    score = result["score"]
    relevance_score = sum(
        1 for word in content.lower().split() if word in user_interests
    )
    relevance_score += score if sentiment == "POSITIVE" else 0
    return relevance_score


def calculate_post_score(
    upvotes: int, downvotes: int, comment_count: int, created_at: datetime
) -> float:
    """
    Calculates the score of a post based on vote difference, comment count, and post age.
    """
    vote_difference = upvotes - downvotes
    age_hours = (datetime.now(timezone.utc) - created_at).total_seconds() / 3600.0
    score = (vote_difference + comment_count) / (age_hours + 2) ** 1.8
    return score


def update_post_score(db: Session, post: models.Post):
    """
    Updates the post's score and commits the changes to the database.
    """
    upvotes = (
        db.query(models.Vote)
        .filter(models.Vote.post_id == post.id, models.Vote.dir == 1)
        .count()
    )
    downvotes = (
        db.query(models.Vote)
        .filter(models.Vote.post_id == post.id, models.Vote.dir == 0)
        .count()
    )
    post.score = calculate_post_score(
        upvotes, downvotes, post.comment_count, post.created_at
    )
    db.commit()


def update_post_vote_statistics(db: Session, post_id: int):
    """
    Updates the vote statistics for a specific post.
    """
    post = db.query(models.Post).filter(models.Post.id == post_id).first()
    if not post:
        return
    stats = post.vote_statistics or models.PostVoteStatistics(post_id=post_id)
    stats.total_votes = (
        db.query(models.Reaction).filter(models.Reaction.post_id == post_id).count()
    )
    stats.upvotes = (
        db.query(models.Vote)
        .filter(models.Vote.post_id == post_id, models.Vote.dir == 1)
        .count()
    )
    stats.downvotes = (
        db.query(models.Vote)
        .filter(models.Vote.post_id == post_id, models.Vote.dir == 0)
        .count()
    )
    for reaction_type in models.ReactionType:
        count = (
            db.query(models.Reaction)
            .filter(
                models.Reaction.post_id == post_id,
                models.Reaction.reaction_type == reaction_type,
            )
            .count()
        )
        setattr(stats, f"{reaction_type.value}_count", count)
    if not post.vote_statistics:
        db.add(stats)
    db.commit()


def get_user_vote_analytics(db: Session, user_id: int) -> schemas.UserVoteAnalytics:
    """
    Generates vote analytics for a user's posts.
    """
    user_posts = db.query(models.Post).filter(models.Post.owner_id == user_id).all()
    total_posts = len(user_posts)
    total_votes = sum(
        post.vote_statistics.total_votes for post in user_posts if post.vote_statistics
    )
    if total_posts == 0:
        return schemas.UserVoteAnalytics(
            total_posts=0,
            total_votes_received=0,
            average_votes_per_post=0,
            most_upvoted_post=None,
            most_downvoted_post=None,
            most_reacted_post=None,
        )
    average_votes = total_votes / total_posts
    most_upvoted = max(
        user_posts, key=lambda p: p.vote_statistics.upvotes if p.vote_statistics else 0
    )
    most_downvoted = max(
        user_posts,
        key=lambda p: p.vote_statistics.downvotes if p.vote_statistics else 0,
    )
    most_reacted = max(
        user_posts,
        key=lambda p: p.vote_statistics.total_votes if p.vote_statistics else 0,
    )
    return schemas.UserVoteAnalytics(
        total_posts=total_posts,
        total_votes_received=total_votes,
        average_votes_per_post=average_votes,
        most_upvoted_post=create_post_vote_analytics(most_upvoted),
        most_downvoted_post=create_post_vote_analytics(most_downvoted),
        most_reacted_post=create_post_vote_analytics(most_reacted),
    )


def create_post_vote_analytics(
    post: models.Post,
) -> Optional[schemas.PostVoteAnalytics]:
    """
    Creates vote analytics data for a specific post.
    """
    stats = post.vote_statistics
    if not stats:
        return None
    total_votes = stats.total_votes or 1  # Avoid division by zero
    upvote_percentage = (stats.upvotes / total_votes) * 100
    downvote_percentage = (stats.downvotes / total_votes) * 100
    reaction_counts = {
        "like": stats.like_count,
        "love": stats.love_count,
        "haha": stats.haha_count,
        "wow": stats.wow_count,
        "sad": stats.sad_count,
        "angry": stats.angry_count,
    }
    most_common_reaction = max(reaction_counts, key=reaction_counts.get)
    return schemas.PostVoteAnalytics(
        post_id=post.id,
        title=post.title,
        statistics=schemas.PostVoteStatistics.from_orm(stats),
        upvote_percentage=upvote_percentage,
        downvote_percentage=downvote_percentage,
        most_common_reaction=most_common_reaction,
    )


# ============================================
# Admin and Exception Handlers
# ============================================
def admin_required(func):
    """
    Decorator to ensure that the current user has admin privileges.
    """

    @wraps(func)
    async def wrapper(*args, **kwargs):
        # Local import to avoid circular dependency
        from .oauth2 import get_current_user

        current_user = await get_current_user()
        if not getattr(current_user, "is_admin", False):
            raise HTTPException(status_code=403, detail="Admin privileges required")
        return await func(*args, **kwargs)

    return wrapper


def handle_exceptions(func):
    """
    Decorator for handling exceptions and returning a standardized error message.
    """

    @wraps(func)
    async def wrapper(*args, **kwargs):
        try:
            return await func(*args, **kwargs)
        except Exception as e:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"An error occurred: {str(e)}",
            )

    return wrapper


# ============================================
# Translation Utilities
# ============================================
@lru_cache(maxsize=1000)
async def cached_translate_text(text: str, source_lang: str, target_lang: str):
    """
    Translates text using caching.
    Note: The 'translate_text' function must be implemented externally.
    """
    cache_key = f"{text}:{source_lang}:{target_lang}"
    if cache_key in translation_cache:
        return translation_cache[cache_key]
    translated_text = await translate_text(text, source_lang, target_lang)
    translation_cache[cache_key] = translated_text
    return translated_text


async def get_translated_content(content: str, user: "User", source_lang: str):
    """
    Returns the translated content if the user's preferred language differs from the source language.
    """
    if user.auto_translate and user.preferred_language != source_lang:
        return await cached_translate_text(
            content, source_lang, user.preferred_language
        )
    return content


# ============================================
# Link Preview Update Function
# ============================================
def update_link_preview(db: Session, message_id: int, url: str):
    """
    Updates the link preview for a message in the database.
    Note: Uses the external 'extract_link_preview' function.
    """
    link_preview = extract_link_preview(url)
    if link_preview:
        db.query(models.Message).filter(models.Message.id == message_id).update(
            {"link_preview": link_preview}
        )
        db.commit()


# ============================================
# User Event Logging Function
# ============================================
def log_user_event(
    db: Session, user_id: int, event: str, metadata: Optional[dict] = None
):
    """
    Logs user events. Currently prints the event; can be modified to store the events in the database.
    """
    log_message = f"User Event - User: {user_id}, Event: {event}, Metadata: {metadata}"
    print(log_message)
