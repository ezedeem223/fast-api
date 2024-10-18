from passlib.context import CryptContext
import re
import qrcode
import base64
from io import BytesIO
import os
from fastapi import UploadFile, Request
import aiofiles
from better_profanity import profanity
import validators
from sklearn.feature_extraction.text import CountVectorizer
from sklearn.naive_bayes import MultinomialNB
import nltk
from nltk.corpus import stopwords
import joblib
import requests
from urllib.parse import urlparse
from textblob import TextBlob
from sqlalchemy.orm import Session
from . import models
from transformers import pipeline
from .config import settings
import secrets
from cryptography.fernet import Fernet
import time
from collections import deque


QUALITY_WINDOW_SIZE = 10
MIN_QUALITY_THRESHOLD = 50

model_name = "microsoft/DialogRPT-offensive"
offensive_classifier = pipeline(
    "text-classification", model=model_name, device=0 if settings.USE_GPU else -1
)

# إعداد التشفير باستخدام bcrypt
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
nltk.download("stopwords", quiet=True)
profanity.load_censor_words()


def hash(password: str) -> str:
    """
    Hashes a password using bcrypt.

    Args:
        password (str): The plain text password to hash.

    Returns:
        str: The hashed password.
    """
    return pwd_context.hash(password)


def verify(plain_password: str, hashed_password: str) -> bool:
    """
    Verifies a plain text password against a hashed password.

    Args:
        plain_password (str): The plain text password.
        hashed_password (str): The hashed password to compare against.

    Returns:
        bool: True if the passwords match, False otherwise.
    """
    return pwd_context.verify(plain_password, hashed_password)


def check_content_against_rules(content: str, rules: List[str]) -> bool:
    for rule in rules:
        if re.search(rule, content, re.IGNORECASE):
            return False
    return True


def create_default_categories(db: Session):
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

            # إضافة تصنيفات فرعية
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


def generate_qr_code(data: str) -> str:
    qr = qrcode.QRCode(version=1, box_size=10, border=5)
    qr.add_data(data)
    qr.make(fit=True)
    img = qr.make_image(fill_color="black", back_color="white")

    buffered = BytesIO()
    img.save(buffered, format="PNG")
    return base64.b64encode(buffered.getvalue()).decode()


def update_user_statistics(db: Session, user_id: int, action: str):
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


async def save_upload_file(upload_file: UploadFile) -> str:
    file_location = f"uploads/{upload_file.filename}"
    async with aiofiles.open(file_location, "wb") as out_file:
        content = await upload_file.read()
        await out_file.write(content)
    return file_location


def train_content_classifier():
    # هذه مجرد بيانات مثالية، يجب استبدالها ببيانات حقيقية
    X = ["This is a good comment", "Bad comment with profanity", "Normal text here"]
    y = [0, 1, 0]  # 0 للمحتوى العادي، 1 للمحتوى غير اللائق

    vectorizer = CountVectorizer(stop_words=stopwords.words("english"))
    X_vectorized = vectorizer.fit_transform(X)

    classifier = MultinomialNB()
    classifier.fit(X_vectorized, y)

    # حفظ النموذج والمحول
    joblib.dump(classifier, "content_classifier.joblib")
    joblib.dump(vectorizer, "content_vectorizer.joblib")


def check_for_profanity(text: str) -> bool:
    """
    Check if the given text contains profanity using both better-profanity and ML model.
    Returns True if profanity is detected, False otherwise.
    """
    # استخدام better-profanity
    if profanity.contains_profanity(text):
        return True

    # استخدام نموذج تعلم الآلة
    if not os.path.exists("content_classifier.joblib"):
        train_content_classifier()

    classifier = joblib.load("content_classifier.joblib")
    vectorizer = joblib.load("content_vectorizer.joblib")

    X_vectorized = vectorizer.transform([text])
    prediction = classifier.predict(X_vectorized)

    return prediction[0] == 1


def validate_urls(text: str) -> bool:
    """
    Check if all URLs in the text are valid.
    Returns True if all URLs are valid, False otherwise.
    """
    words = text.split()
    urls = [word for word in words if word.startswith(("http://", "https://"))]
    return all(validators.url(url) for url in urls)


def is_valid_image_url(url: str) -> bool:
    try:
        response = requests.head(url)
        return response.headers.get("content-type", "").startswith("image/")
    except:
        return False


def is_valid_video_url(url: str) -> bool:
    parsed_url = urlparse(url)
    video_hosts = ["youtube.com", "vimeo.com", "dailymotion.com"]
    return any(host in parsed_url.netloc for host in video_hosts)


def analyze_sentiment(text):
    analysis = TextBlob(text)
    return analysis.sentiment.polarity


def get_client_ip(request: Request):
    forwarded_for = request.headers.get("X-Forwarded-For")
    if forwarded_for:
        return forwarded_for.split(",")[0].strip()
    return request.client.host


def is_ip_banned(db: Session, ip_address: str):
    ban = db.query(models.IPBan).filter(models.IPBan.ip_address == ip_address).first()
    if ban:
        if ban.expires_at and ban.expires_at < datetime.now():
            db.delete(ban)
            db.commit()
            return False
        return True
    return False


def detect_ip_evasion(db: Session, user_id: int, current_ip: str):
    user_ips = (
        db.query(models.UserSession.ip_address)
        .filter(models.UserSession.user_id == user_id)
        .distinct()
        .all()
    )
    user_ips = [ip[0] for ip in user_ips]

    for ip in user_ips:
        if (
            ip != current_ip
            and ipaddress.ip_address(ip).is_private
            != ipaddress.ip_address(current_ip).is_private
        ):
            return True
    return False


def update_banned_words_cache(db: Session):
    banned_words = db.query(models.BannedWord).all()
    # يمكنك تخزين هذه القائمة في ذاكرة التخزين المؤقت أو قاعدة بيانات في الذاكرة للوصول السريع
    # مثال باستخدام متغير عام (ليس الحل الأمثل للإنتاج):
    global BANNED_WORDS_CACHE
    BANNED_WORDS_CACHE = {word.word: word.severity for word in banned_words}


def update_ban_statistics(
    db: Session, ban_type: str, reason: str, effectiveness: float
):
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

    # Обновление наиболее распространенной причины бана
    ban_reason = (
        db.query(models.BanReason).filter(models.BanReason.reason == reason).first()
    )
    if ban_reason:
        ban_reason.count += 1
        ban_reason.last_used = datetime.now()
    else:
        new_reason = models.BanReason(reason=reason)
        db.add(new_reason)

    # Обновление эффективности бана
    stats.effectiveness_score = (
        stats.effectiveness_score * (stats.total_bans - 1) + effectiveness
    ) / stats.total_bans

    db.commit()


def log_user_event(db: Session, user_id: int, event_type: str, details: dict = None):
    event = models.UserEvent(user_id=user_id, event_type=event_type, details=details)
    db.add(event)
    db.commit()


def get_or_create_hashtag(db: Session, hashtag_name: str):
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


def process_mentions(content: str, db: Session):
    mentioned_usernames = re.findall(r"@(\w+)", content)
    mentioned_users = []
    for username in mentioned_usernames:
        user = db.query(models.User).filter(models.User.username == username).first()
        if user:
            mentioned_users.append(user)
    return mentioned_users


def is_content_offensive(text: str) -> tuple:
    """
    فحص النص للكشف عن المحتوى المسيء باستخدام نموذج الذكاء الاصطناعي.

    :param text: النص المراد فحصه
    :return: زوج يحتوي على (هل النص مسيء، درجة الثقة)
    """
    result = offensive_classifier(text)[0]
    is_offensive = result["label"] == "LABEL_1" and result["score"] > 0.8
    return is_offensive, result["score"]


def generate_encryption_key():
    return Fernet.generate_key().decode()


def update_encryption_key(old_key):
    new_key = Fernet.generate_key()
    old_fernet = Fernet(old_key.encode())
    new_fernet = Fernet(new_key)

    # Здесь вы можете добавить логику для повторного шифрования данных с новым ключом, если это необходимо

    return new_key.decode()


class CallQualityBuffer:
    def __init__(self, window_size=QUALITY_WINDOW_SIZE):
        self.window_size = window_size
        self.quality_scores = deque(maxlen=window_size)
        self.last_update_time = time.time()

    def add_score(self, score):
        self.quality_scores.append(score)
        self.last_update_time = time.time()

    def get_average_score(self):
        if not self.quality_scores:
            return 100  # افتراض الجودة الممتازة إذا لم يتم تسجيل أي قياسات
        return sum(self.quality_scores) / len(self.quality_scores)


quality_buffers = {}


def check_call_quality(data, call_id):
    # استخراج معلومات الجودة من البيانات المستلمة
    packet_loss = data.get("packet_loss", 0)
    latency = data.get("latency", 0)
    jitter = data.get("jitter", 0)

    # حساب درجة الجودة (هذه مجرد صيغة بسيطة، يمكنك تعديلها حسب احتياجاتك)
    quality_score = 100 - (packet_loss * 2 + latency / 10 + jitter)

    # تحديث التخزين المؤقت للجودة
    if call_id not in quality_buffers:
        quality_buffers[call_id] = CallQualityBuffer()

    quality_buffers[call_id].add_score(quality_score)

    # الحصول على متوسط الجودة
    average_quality = quality_buffers[call_id].get_average_score()

    return average_quality


def should_adjust_video_quality(call_id):
    if call_id in quality_buffers:
        average_quality = quality_buffers[call_id].get_average_score()
        return average_quality < MIN_QUALITY_THRESHOLD
    return False


def get_recommended_video_quality(call_id):
    if call_id in quality_buffers:
        average_quality = quality_buffers[call_id].get_average_score()
        if average_quality < 30:
            return "low"
        elif average_quality < 60:
            return "medium"
        else:
            return "high"
    return "high"  # افتراض الجودة العالية إذا لم تتوفر بيانات


def clean_old_quality_buffers():
    current_time = time.time()
    for call_id in list(quality_buffers.keys()):
        if current_time - quality_buffers[call_id].last_update_time > 300:  # 5 دقائق
            del quality_buffers[call_id]
