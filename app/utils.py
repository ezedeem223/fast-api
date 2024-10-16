from passlib.context import CryptContext
import re
import qrcode
import base64
from io import BytesIO
import os
from fastapi import UploadFile
import aiofiles
from better_profanity import profanity
import validators
from sklearn.feature_extraction.text import CountVectorizer
from sklearn.naive_bayes import MultinomialNB
import nltk
from nltk.corpus import stopwords
import joblib


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
