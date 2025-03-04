# ================================
# Import statements and dependencies
# ================================
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
from .oauth2 import get_current_user
import requests
from urllib.parse import urlparse
from textblob import TextBlob
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
import ipaddress
from typing import List, Optional

# Note: translate_text, SortOption, and extract_link_preview should be defined elsewhere.
# from .some_module import translate_text, extract_link_preview  # Placeholder for external definitions
# from .schemas import SortOption  # Assuming SortOption is defined in schemas
# from .models import User  # Assuming a User model exists

# ================================
# Global variables and constants
# ================================
spell = SpellChecker()
translation_cache = TTLCache(maxsize=1000, ttl=3600)

QUALITY_WINDOW_SIZE = 10
MIN_QUALITY_THRESHOLD = 50

# Offensive content classifier initialization
model_name = "microsoft/DialogRPT-offensive"
offensive_classifier = pipeline(
    "text-classification", model=model_name, device=0 if settings.USE_GPU else -1
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


# ================================
# Authentication Utilities
# ================================
def hash(password: str) -> str:
    """Hash the given password using bcrypt."""
    return pwd_context.hash(password)


def verify(plain_password: str, hashed_password: str) -> bool:
    """Verify the plain password against the hashed password."""
    return pwd_context.verify(plain_password, hashed_password)


# ================================
# Content Moderation and Validation Functions
# ================================
def check_content_against_rules(content: str, rules: List[str]) -> bool:
    """Check if content violates any given regex-based rules."""
    for rule in rules:
        if re.search(rule, content, re.IGNORECASE):
            return False
    return True


def train_content_classifier():
    """
    Train a simple classifier for content moderation.
    Note: Replace dummy data with real data for production.
    """
    X = ["This is a good comment", "Bad comment with profanity", "Normal text here"]
    y = [0, 1, 0]  # 0: normal content, 1: offensive content

    vectorizer = CountVectorizer(stop_words=stopwords.words("english"))
    X_vectorized = vectorizer.fit_transform(X)

    classifier = MultinomialNB()
    classifier.fit(X_vectorized, y)

    # Save the classifier and vectorizer
    joblib.dump(classifier, "content_classifier.joblib")
    joblib.dump(vectorizer, "content_vectorizer.joblib")


def check_for_profanity(text: str) -> bool:
    """
    Check if the text contains profanity using better-profanity and a machine learning model.
    Returns True if profanity is detected.
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
    Validate that all URLs in the text are proper URLs.
    Returns True if all URLs are valid.
    """
    words = text.split()
    urls = [word for word in words if word.startswith(("http://", "https://"))]
    return all(validators.url(url) for url in urls)


def is_valid_image_url(url: str) -> bool:
    """Check if the URL points to an image resource."""
    try:
        response = requests.head(url)
        return response.headers.get("content-type", "").startswith("image/")
    except:
        return False


def is_valid_video_url(url: str) -> bool:
    """Check if the URL belongs to a supported video hosting service."""
    parsed_url = urlparse(url)
    video_hosts = ["youtube.com", "vimeo.com", "dailymotion.com"]
    return any(host in parsed_url.netloc for host in video_hosts)


def analyze_sentiment(text):
    """Analyze the sentiment of the text using TextBlob."""
    analysis = TextBlob(text)
    return analysis.sentiment.polarity


# ================================
# QR Code and File Upload Functions
# ================================
def generate_qr_code(data: str) -> str:
    """Generate a QR code for the given data and return it as a base64-encoded PNG."""
    qr = qrcode.QRCode(version=1, box_size=10, border=5)
    qr.add_data(data)
    qr.make(fit=True)
    img = qr.make_image(fill_color="black", back_color="white")
    buffered = BytesIO()
    img.save(buffered, format="PNG")
    return base64.b64encode(buffered.getvalue()).decode()


async def save_upload_file(upload_file: UploadFile) -> str:
    """Save an uploaded file asynchronously and return its storage path."""
    file_location = f"uploads/{upload_file.filename}"
    async with aiofiles.open(file_location, "wb") as out_file:
        content = await upload_file.read()
        await out_file.write(content)
    return file_location


# ================================
# Default Categories and Statistics Functions
# ================================
def create_default_categories(db: Session):
    """Create default post categories and their sub-categories if not already present."""
    default_categories = [
        {"name": "عمل", "description": "منشورات متعلقة بفرص العمل"},
        {"name": "هجرة", "description": "معلومات وتجارب عن الهجرة"},
        {"name": "لجوء", "description": "منشورات حول عملية اللجوء"},
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

            # Adding sub-categories
            if category["name"] == "عمل":
                sub_categories = ["عمل في كندا", "عمل في أمريكا", "عمل في أوروبا"]
            elif category["name"] == "هجرة":
                sub_categories = [
                    "هجرة إلى كندا",
                    "هجرة إلى أمريكا",
                    "هجرة إلى أستراليا",
                ]
            elif category["name"] == "لجوء":
                sub_categories = ["لجوء في أوروبا", "لجوء في كندا", "لجوء في أمريكا"]

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
    """Update user statistics based on the performed action (post, comment, like, view)."""
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


# ================================
# IP and Ban Management Functions
# ================================
def get_client_ip(request: Request):
    """Retrieve the client IP address from the request headers."""
    forwarded_for = request.headers.get("X-Forwarded-For")
    if forwarded_for:
        return forwarded_for.split(",")[0].strip()
    return request.client.host


def is_ip_banned(db: Session, ip_address: str):
    """
    Check if an IP address is banned.
    If the ban has expired, it will be removed.
    """
    ban = db.query(models.IPBan).filter(models.IPBan.ip_address == ip_address).first()
    if ban:
        if ban.expires_at and ban.expires_at < datetime.now():
            db.delete(ban)
            db.commit()
            return False
        return True
    return False


def detect_ip_evasion(db: Session, user_id: int, current_ip: str):
    """
    Detect if the user is using different IP addresses (e.g., evasion).
    Compares the current IP with previously used IPs.
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


def update_banned_words_cache(db: Session):
    """
    Update the cache of banned words from the database.
    This is a simple example; in production, a more robust solution may be needed.
    """
    banned_words = db.query(models.BannedWord).all()
    global BANNED_WORDS_CACHE
    BANNED_WORDS_CACHE = {word.word: word.severity for word in banned_words}


def update_ban_statistics(
    db: Session, ban_type: str, reason: str, effectiveness: float
):
    """
    Update ban statistics such as total bans, type-specific counts, and effectiveness score.
    """
    today = date.today()
    stats = (
        db.query(models.BanStatistics)
        .filter(models.BanStatistics.date == today)
        .first()
    )
    if not stats:
        stats = models.BanStatistics(date=today)
        db.add(stats)

    stats.total_bans += 1
    setattr(stats, f"{ban_type}_bans", getattr(stats, f"{ban_type}_bans") + 1)

    ban_reason = (
        db.query(models.BanReason).filter(models.BanReason.reason == reason).first()
    )
    if ban_reason:
        ban_reason.count += 1
        ban_reason.last_used = datetime.now()
    else:
        new_reason = models.BanReason(reason=reason)
        db.add(new_reason)

    stats.effectiveness_score = (
        stats.effectiveness_score * (stats.total_bans - 1) + effectiveness
    ) / stats.total_bans
    db.commit()


def log_user_event(db: Session, user_id: int, event_type: str, details: dict = None):
    """Log a user event into the database."""
    event = models.UserEvent(user_id=user_id, event_type=event_type, details=details)
    db.add(event)
    db.commit()


# ================================
# Hashtag and Repost Functions
# ================================
def get_or_create_hashtag(db: Session, hashtag_name: str):
    """Retrieve an existing hashtag or create a new one."""
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
    """Update statistics related to reposts for a given post."""
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
    """Send a notification when a post is reposted."""
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


# ================================
# Mentions and Offensive Content
# ================================
def process_mentions(content: str, db: Session):
    """Extract and process user mentions in the content."""
    mentioned_usernames = re.findall(r"@(\w+)", content)
    mentioned_users = []
    for username in mentioned_usernames:
        user = db.query(models.User).filter(models.User.username == username).first()
        if user:
            mentioned_users.append(user)
    return mentioned_users


def is_content_offensive(text: str) -> tuple:
    """
    Check if the text is offensive using an AI model.
    Returns a tuple (is_offensive, score).
    """
    result = offensive_classifier(text)[0]
    is_offensive = result["label"] == "LABEL_1" and result["score"] > 0.8
    return is_offensive, result["score"]


# ================================
# Encryption Key Functions
# ================================
def generate_encryption_key():
    """Generate a new encryption key using Fernet."""
    return Fernet.generate_key().decode()


def update_encryption_key(old_key):
    """
    Update the encryption key.
    Note: Add logic for re-encrypting data if necessary.
    """
    new_key = Fernet.generate_key()
    old_fernet = Fernet(old_key.encode())
    new_fernet = Fernet(new_key)
    return new_key.decode()


# ================================
# Call Quality and Video Adjustment Functions
# ================================
class CallQualityBuffer:
    """A buffer class to store recent call quality scores."""

    def __init__(self, window_size=QUALITY_WINDOW_SIZE):
        self.window_size = window_size
        self.quality_scores = deque(maxlen=window_size)
        self.last_update_time = time.time()

    def add_score(self, score):
        """Add a new quality score to the buffer."""
        self.quality_scores.append(score)
        self.last_update_time = time.time()

    def get_average_score(self):
        """Compute the average quality score."""
        if not self.quality_scores:
            return 100  # Assume excellent quality if no scores recorded
        return sum(self.quality_scores) / len(self.quality_scores)


quality_buffers = {}


def check_call_quality(data, call_id):
    """
    Calculate call quality based on packet loss, latency, and jitter.
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


def should_adjust_video_quality(call_id):
    """Determine if video quality should be adjusted based on average quality score."""
    if call_id in quality_buffers:
        average_quality = quality_buffers[call_id].get_average_score()
        return average_quality < MIN_QUALITY_THRESHOLD
    return False


def get_recommended_video_quality(call_id):
    """Recommend video quality level based on average quality score."""
    if call_id in quality_buffers:
        average_quality = quality_buffers[call_id].get_average_score()
        if average_quality < 30:
            return "low"
        elif average_quality < 60:
            return "medium"
        else:
            return "high"
    return "high"  # Default to high quality if no data


def clean_old_quality_buffers():
    """Remove call quality buffers that haven't been updated for over 5 minutes."""
    current_time = time.time()
    for call_id in list(quality_buffers.keys()):
        if current_time - quality_buffers[call_id].last_update_time > 300:  # 5 minutes
            del quality_buffers[call_id]


# ================================
# Search and Spellcheck Functions
# ================================
def update_search_vector():
    """Update the full-text search vector for posts in the database."""
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
    """Search posts by text query using full-text search and media text matching."""
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
    """Generate spell check suggestions for the query."""
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
    Format spell suggestions if the corrected query differs from the original.
    Returns a suggestion string if applicable.
    """
    if original_query.lower() != " ".join(suggestions).lower():
        return f"هل تقصد: {' '.join(suggestions)}?"
    return ""


def sort_search_results(query, sort_option: "SortOption", db: Session):
    """Sort search results based on relevance, date, or popularity."""
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


# ================================
# User Behavior and Post Scoring Functions
# ================================
def analyze_user_behavior(user_history, content):
    """
    Analyze user behavior based on search history and content sentiment.
    Returns a relevance score.
    """
    user_interests = set(item.lower() for item in user_history)
    result = sentiment_pipeline(content[:512])[0]  # Limit text to 512 characters
    sentiment = result["label"]
    score = result["score"]
    relevance_score = sum(
        1 for word in content.lower().split() if word in user_interests
    )
    relevance_score += score if sentiment == "POSITIVE" else 0
    return relevance_score


def calculate_post_score(upvotes, downvotes, comment_count, created_at):
    """
    Calculate the score of a post based on votes, comment count, and post age.
    """
    vote_difference = upvotes - downvotes
    age_hours = (datetime.now(timezone.utc) - created_at).total_seconds() / 3600.0
    score = (vote_difference + comment_count) / (age_hours + 2) ** 1.8
    return score


def update_post_score(db: Session, post: models.Post):
    """Update the score of a post and commit the changes to the database."""
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
    """Update vote statistics for a post."""
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
    """Generate vote analytics for a user's posts."""
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


def create_post_vote_analytics(post: models.Post) -> schemas.PostVoteAnalytics:
    """Create analytics data for a specific post based on vote statistics."""
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


# ================================
# Admin and Exception Handlers
# ================================
def admin_required(func):
    """Decorator to ensure the current user has admin privileges."""

    @wraps(func)
    async def wrapper(*args, **kwargs):
        current_user = await get_current_user()
        if not current_user.is_admin:
            raise HTTPException(status_code=403, detail="Admin privileges required")
        return await func(*args, **kwargs)

    return wrapper


def handle_exceptions(func):
    """Decorator to handle exceptions and return a standardized error response."""

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


# ================================
# Translation Utilities
# ================================
@lru_cache(maxsize=1000)
async def cached_translate_text(text: str, source_lang: str, target_lang: str):
    """
    Translate text using caching.
    Note: The function 'translate_text' must be implemented elsewhere.
    """
    cache_key = f"{text}:{source_lang}:{target_lang}"
    if cache_key in translation_cache:
        return translation_cache[cache_key]
    translated_text = await translate_text(
        text, source_lang, target_lang
    )  # External function
    translation_cache[cache_key] = translated_text
    return translated_text


async def get_translated_content(content: str, user: "User", source_lang: str):
    """
    Return translated content if the user's preferred language differs from the source.
    Note: The 'User' model should be defined in your project.
    """
    if user.auto_translate and user.preferred_language != source_lang:
        return await cached_translate_text(
            content, source_lang, user.preferred_language
        )
    return content


# ================================
# Link Preview Update Function
# ================================
def update_link_preview(db: Session, message_id: int, url: str):
    """
    Update the link preview for a message.
    Note: The function 'extract_link_preview' should be defined elsewhere.
    """
    link_preview = extract_link_preview(
        url
    )  # This function must be implemented in another module
    if link_preview:
        db.query(models.Message).filter(models.Message.id == message_id).update(
            {"link_preview": link_preview}
        )
        db.commit()


# =====================================================================
# End of merged utils.py
# =====================================================================
