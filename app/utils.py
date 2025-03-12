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

# تم إزالة الاستيراد التالي لتفادي الاستيراد الدائري:
# from .oauth2 import get_current_user
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

# استيراد SpellChecker
from spellchecker import SpellChecker
import ipaddress  # إضافة مكتبة ipaddress
from langdetect import detect, LangDetectException

# Note: translate_text, SortOption, and extract_link_preview should be defined elsewhere.
# from .some_module import translate_text, extract_link_preview  # Placeholder for external definitions
# from .schemas import SortOption  # Assuming SortOption is defined in schemas
# from .models import User  # Assuming a User model exists

# ================================
# Global variables and constants
# ================================
spell = SpellChecker()
translation_cache = TTLCache(maxsize=1000, ttl=3600)
cache = TTLCache(maxsize=100, ttl=60)  # تعريف متغير cache للتخزين المؤقت

QUALITY_WINDOW_SIZE = 10
MIN_QUALITY_THRESHOLD = 50

# Offensive content classifier initialization
# تم استبدال النموذج السابق بنموذج صالح من Hugging Face لاكتشاف المحتوى المسيء
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


# ================================
# Authentication Utilities
# ================================
def hash(password: str) -> str:
    """تشفير كلمة المرور باستخدام bcrypt."""
    return pwd_context.hash(password)


def verify(plain_password: str, hashed_password: str) -> bool:
    """التحقق من كلمة المرور العادية مقابل كلمة المرور المشفرة."""
    return pwd_context.verify(plain_password, hashed_password)


# ================================
# Content Moderation and Validation Functions
# ================================
def check_content_against_rules(content: str, rules: List[str]) -> bool:
    """التحقق مما إذا كان المحتوى ينتهك أي من القواعد المعتمدة على التعابير النمطية."""
    for rule in rules:
        if re.search(rule, content, re.IGNORECASE):
            return False
    return True


def detect_language(text: str) -> str:
    """
    تحدد هذه الدالة لغة النص المُعطى وتعيد رمز اللغة.
    في حال حدوث خطأ تعيد 'unknown'.
    """
    try:
        return detect(text)
    except LangDetectException:
        return "unknown"


def train_content_classifier():
    """
    تدريب مصنف بسيط لتصفية المحتوى.
    ملاحظة: استبدل البيانات الوهمية ببيانات حقيقية في بيئة الإنتاج.
    """
    X = ["This is a good comment", "Bad comment with profanity", "Normal text here"]
    y = [0, 1, 0]  # 0: محتوى عادي، 1: محتوى مسيء

    vectorizer = CountVectorizer(stop_words=stopwords.words("english"))
    X_vectorized = vectorizer.fit_transform(X)

    classifier = MultinomialNB()
    classifier.fit(X_vectorized, y)

    # حفظ المصنف والمحول النصي
    joblib.dump(classifier, "content_classifier.joblib")
    joblib.dump(vectorizer, "content_vectorizer.joblib")


def check_for_profanity(text: str) -> bool:
    """
    التحقق مما إذا كان النص يحتوي على كلمات مسيئة باستخدام better-profanity ونموذج تعلم آلي.
    يُعيد True إذا تم اكتشاف كلمات مسيئة.
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
    التحقق من صحة جميع روابط URL الموجودة في النص.
    يُعيد True إذا كانت جميع الروابط صحيحة.
    """
    words = text.split()
    urls = [word for word in words if word.startswith(("http://", "https://"))]
    return all(validators.url(url) for url in urls)


def is_valid_image_url(url: str) -> bool:
    """التحقق مما إذا كان الرابط يشير إلى مورد صورة."""
    try:
        import requests

        response = requests.head(url)
        return response.headers.get("content-type", "").startswith("image/")
    except:
        return False


def is_valid_video_url(url: str) -> bool:
    """التحقق مما إذا كان الرابط يعود إلى خدمة استضافة فيديو مدعومة."""
    from urllib.parse import urlparse

    parsed_url = urlparse(url)
    video_hosts = ["youtube.com", "vimeo.com", "dailymotion.com"]
    return any(host in parsed_url.netloc for host in video_hosts)


def analyze_sentiment(text):
    """تحليل معنويات النص باستخدام TextBlob."""
    from textblob import TextBlob

    analysis = TextBlob(text)
    return analysis.sentiment.polarity


# ================================
# QR Code and File Upload Functions
# ================================
def generate_qr_code(data: str) -> str:
    """إنشاء رمز QR للبيانات المُعطاة وإرجاعه بصيغة PNG مشفر ب base64."""
    qr = qrcode.QRCode(version=1, box_size=10, border=5)
    qr.add_data(data)
    qr.make(fit=True)
    img = qr.make_image(fill_color="black", back_color="white")
    buffered = BytesIO()
    img.save(buffered, format="PNG")
    return base64.b64encode(buffered.getvalue()).decode()


async def save_upload_file(upload_file: UploadFile) -> str:
    """حفظ الملف المرفوع بشكل غير متزامن وإرجاع مسار التخزين."""
    file_location = f"uploads/{upload_file.filename}"
    async with aiofiles.open(file_location, "wb") as out_file:
        content = await upload_file.read()
        await out_file.write(content)
    return file_location


# ================================
# Default Categories and Statistics Functions
# ================================
def create_default_categories(db: Session):
    """إنشاء الفئات الافتراضية للمنشورات والفئات الفرعية إذا لم تكن موجودة."""
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

            # إضافة الفئات الفرعية
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
    """تحديث إحصائيات المستخدم بناءً على الإجراء (منشور، تعليق، إعجاب، مشاهدة)."""
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
# دوال إدارة IP والبن (لم يتم فصلها)
# ================================
def get_client_ip(request: Request):
    """
    استرجاع عنوان IP الخاص بالعميل من رؤوس الطلب.
    """
    forwarded_for = request.headers.get("X-Forwarded-For")
    if forwarded_for:
        return forwarded_for.split(",")[0].strip()
    return request.client.host


def is_ip_banned(db: Session, ip_address: str):
    """
    التحقق مما إذا كان عنوان الـ IP محظوراً.
    إذا انتهت صلاحية الحظر، يتم إزالته.
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
    الكشف عن استخدام المستخدم لعناوين IP مختلفة (كإجراء للتحايل).
    يتم مقارنة الـ IP الحالي مع العناوين المستخدمة سابقاً.
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


# ================================
# Hashtag and Repost Functions
# ================================
def get_or_create_hashtag(db: Session, hashtag_name: str):
    """استرجاع هاشتاج موجود أو إنشاء جديد."""
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
    """تحديث الإحصائيات المتعلقة بإعادة نشر منشور معين."""
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
    """إرسال إشعار عند إعادة نشر منشور."""
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
    """استخراج ومعالجة الإشارات (mentions) في المحتوى."""
    mentioned_usernames = re.findall(r"@(\w+)", content)
    mentioned_users = []
    for username in mentioned_usernames:
        user = db.query(models.User).filter(models.User.username == username).first()
        if user:
            mentioned_users.append(user)
    return mentioned_users


def is_content_offensive(text: str) -> tuple:
    """
    التحقق مما إذا كان النص مسيئاً باستخدام نموذج ذكاء اصطناعي.
    يُعيد (is_offensive, score) حيث is_offensive هو قيمة منطقية.
    """
    result = offensive_classifier(text)[0]
    is_offensive = result["label"] == "LABEL_1" and result["score"] > 0.8
    return is_offensive, result["score"]


# ================================
# Encryption Key Functions
# ================================
def generate_encryption_key():
    """توليد مفتاح تشفير جديد باستخدام Fernet."""
    return Fernet.generate_key().decode()


def update_encryption_key(old_key):
    """
    تحديث مفتاح التشفير.
    ملاحظة: يمكن إضافة منطق لإعادة تشفير البيانات إذا لزم الأمر.
    """
    new_key = Fernet.generate_key()
    old_fernet = Fernet(old_key.encode())
    new_fernet = Fernet(new_key)
    return new_key.decode()


# ================================
# Call Quality and Video Adjustment Functions
# ================================
class CallQualityBuffer:
    """فئة لتخزين درجات جودة المكالمات في نافذة زمنية محددة."""

    def __init__(self, window_size=QUALITY_WINDOW_SIZE):
        self.window_size = window_size
        self.quality_scores = deque(maxlen=window_size)
        self.last_update_time = time.time()

    def add_score(self, score):
        """إضافة درجة جديدة إلى النافذة."""
        self.quality_scores.append(score)
        self.last_update_time = time.time()

    def get_average_score(self):
        """حساب متوسط درجات الجودة."""
        if not self.quality_scores:
            return 100  # نفترض جودة ممتازة في حال عدم تسجيل درجات
        return sum(self.quality_scores) / len(self.quality_scores)


quality_buffers = {}


def check_call_quality(data, call_id):
    """
    حساب جودة المكالمة بناءً على فقدان الحزم والكمون والتذبذب.
    يُعيد متوسط درجة الجودة.
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
    """تحديد ما إذا كان يجب تعديل جودة الفيديو بناءً على متوسط الجودة."""
    if call_id in quality_buffers:
        average_quality = quality_buffers[call_id].get_average_score()
        return average_quality < MIN_QUALITY_THRESHOLD
    return False


def get_recommended_video_quality(call_id):
    """اقتراح مستوى جودة الفيديو بناءً على متوسط درجة الجودة."""
    if call_id in quality_buffers:
        average_quality = quality_buffers[call_id].get_average_score()
        if average_quality < 30:
            return "low"
        elif average_quality < 60:
            return "medium"
        else:
            return "high"
    return "high"  # افتراضي عند عدم وجود بيانات


def clean_old_quality_buffers():
    """إزالة مخازن جودة المكالمات التي لم يتم تحديثها لأكثر من 5 دقائق."""
    current_time = time.time()
    for call_id in list(quality_buffers.keys()):
        if current_time - quality_buffers[call_id].last_update_time > 300:
            del quality_buffers[call_id]


# ================================
# Search and Spellcheck Functions
# ================================
def update_search_vector():
    """تحديث متجه البحث الكامل للمنشورات في قاعدة البيانات."""
    from sqlalchemy import create_engine  # تأكد من تعريف engine بشكل صحيح

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
    """البحث عن المنشورات باستخدام استعلام نصي."""
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
    """توليد اقتراحات إملائية للاستعلام."""
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
    تنسيق اقتراحات الإملاء في حال اختلف الاستعلام المصحح عن الأصلي.
    يُعيد نص الاقتراح إذا كان ذلك مناسباً.
    """
    if original_query.lower() != " ".join(suggestions).lower():
        return f"هل تقصد: {' '.join(suggestions)}?"
    return ""


def sort_search_results(query, sort_option: str, db: Session):
    """ترتيب نتائج البحث بناءً على الصلة أو التاريخ أو الشعبية."""
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
    تحليل سلوك المستخدم بناءً على سجل البحث ومعنويات المحتوى.
    يُعيد درجة صلة.
    """
    user_interests = set(item.lower() for item in user_history)
    result = sentiment_pipeline(content[:512])[0]  # تحديد الطول الأقصى للنص
    sentiment = result["label"]
    score = result["score"]
    relevance_score = sum(
        1 for word in content.lower().split() if word in user_interests
    )
    relevance_score += score if sentiment == "POSITIVE" else 0
    return relevance_score


def calculate_post_score(upvotes, downvotes, comment_count, created_at):
    """
    حساب درجة المنشور بناءً على الأصوات وعدد التعليقات وعمر المنشور.
    """
    vote_difference = upvotes - downvotes
    age_hours = (datetime.now(timezone.utc) - created_at).total_seconds() / 3600.0
    score = (vote_difference + comment_count) / (age_hours + 2) ** 1.8
    return score


def update_post_score(db: Session, post: models.Post):
    """تحديث درجة المنشور وحفظ التغييرات في قاعدة البيانات."""
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
    """تحديث إحصائيات الأصوات لمنشور معين."""
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
    """إنشاء تحليلات للأصوات لمنشورات المستخدم."""
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
    """إنشاء بيانات تحليلات للأصوات لمنشور معين."""
    stats = post.vote_statistics
    if not stats:
        return None
    total_votes = stats.total_votes or 1  # لتفادي القسمة على الصفر
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
    """ديكوريتور للتأكد من أن المستخدم الحالي لديه صلاحيات المسؤول."""

    @wraps(func)
    async def wrapper(*args, **kwargs):
        # استيراد محلي لتفادي الاستيراد الدائري
        from .oauth2 import get_current_user

        current_user = await get_current_user()
        if not getattr(current_user, "is_admin", False):
            raise HTTPException(status_code=403, detail="Admin privileges required")
        return await func(*args, **kwargs)

    return wrapper


def handle_exceptions(func):
    """ديكوريتور للتعامل مع الاستثناءات وإرجاع رسالة خطأ موحدة."""

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
    ترجمة النص مع استخدام التخزين المؤقت.
    ملاحظة: يجب تعريف دالة translate_text في وحدة أخرى.
    """
    cache_key = f"{text}:{source_lang}:{target_lang}"
    if cache_key in translation_cache:
        return translation_cache[cache_key]
    translated_text = await translate_text(
        text, source_lang, target_lang
    )  # دالة خارجية
    translation_cache[cache_key] = translated_text
    return translated_text


async def get_translated_content(content: str, user: "User", source_lang: str):
    """
    إعادة المحتوى المترجم إذا كانت لغة المستخدم المفضلة تختلف عن المصدر.
    ملاحظة: يجب تعريف نموذج User في مشروعك.
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
    تحديث معاينة الرابط للرسالة.
    ملاحظة: يجب تعريف دالة extract_link_preview في وحدة أخرى.
    """
    link_preview = extract_link_preview(url)  # دالة خارجية
    if link_preview:
        db.query(models.Message).filter(models.Message.id == message_id).update(
            {"link_preview": link_preview}
        )
        db.commit()


# ================================
# User Event Logging Function
# ================================
def log_user_event(
    db: Session, user_id: int, event: str, metadata: Optional[dict] = None
):
    """
    تسجل هذه الدالة أحداث المستخدمين في النظام.
    في هذا التطبيق البسيط نقوم بطباعة الحدث في وحدة التحكم.
    يمكنك تعديلها لتخزين الأحداث في قاعدة البيانات إذا كان لديك نموذج مناسب.
    """
    log_message = f"User Event - User: {user_id}, Event: {event}, Metadata: {metadata}"
    print(log_message)
