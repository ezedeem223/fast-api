import os
import logging
from functools import cached_property
from pathlib import Path
from typing import ClassVar, Optional

from dotenv import load_dotenv
from pydantic import EmailStr, Extra, PrivateAttr
from pydantic_settings import BaseSettings, SettingsConfigDict

from fastapi_mail import ConnectionConfig, FastMail
import redis

# تحميل ملف .env
load_dotenv()

# إزالة المتغيرات البيئية غير المطلوبة لتفادي أخطاء التحقق
os.environ.pop("MAIL_TLS", None)
os.environ.pop("MAIL_SSL", None)


def _read_bool_env(var_name: str, default: bool = False) -> bool:
    """Parse a boolean environment variable in a robust way."""

    raw_value = os.getenv(var_name)
    if raw_value is None:
        return default
    return raw_value.strip().lower() in {"1", "true", "yes", "on"}

# إعدادات تسجيل الأخطاء
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


# تحديد المسار الجذري للتطبيق لاستخدامه في القيم الافتراضية
BASE_DIR = Path(__file__).resolve().parent.parent


# إنشاء صنف مخصص لتعطيل التحقق من الحقول الإضافية في إعدادات البريد الإلكتروني
class CustomConnectionConfig(ConnectionConfig):
    class Config:
        extra = Extra.ignore


class Settings(BaseSettings):
    # إعدادات الذكاء الاصطناعي
    AI_MODEL_PATH: str = "bigscience/bloom-1b7"
    AI_MAX_LENGTH: int = 150
    AI_TEMPERATURE: float = 0.7

    # إعدادات قاعدة البيانات
    database_hostname: Optional[str] = os.getenv("DATABASE_HOSTNAME")
    database_port: Optional[str] = os.getenv("DATABASE_PORT")
    database_password: Optional[str] = os.getenv("DATABASE_PASSWORD")
    database_name: Optional[str] = os.getenv("DATABASE_NAME")
    database_username: Optional[str] = os.getenv("DATABASE_USERNAME")
    database_url_override: Optional[str] = os.getenv("DATABASE_URL")

    # إعدادات الأمان
    secret_key: str = os.getenv("SECRET_KEY", "test_secret_key")
    algorithm: str = os.getenv("ALGORITHM", "RS256")
    access_token_expire_minutes: int = int(os.getenv("ACCESS_TOKEN_EXPIRE_MINUTES", 30))

    # إعدادات خدمات الجهات الخارجية
    google_client_id: str = os.getenv("GOOGLE_CLIENT_ID", "default_google_client_id")
    google_client_secret: str = os.getenv(
        "GOOGLE_CLIENT_SECRET", "default_google_client_secret"
    )
    # REDDIT_CLIENT_ID: str = os.getenv("REDDIT_CLIENT_ID", "default_reddit_client_id")
    # REDDIT_CLIENT_SECRET: str = os.getenv("REDDIT_CLIENT_SECRET", "default_reddit_client_secret")

    # إعدادات البريد الإلكتروني
    mail_username: str = os.getenv("MAIL_USERNAME", "noreply@example.com")
    mail_password: str = os.getenv("MAIL_PASSWORD", "password")
    mail_from: EmailStr = os.getenv("MAIL_FROM", "noreply@example.com")
    mail_port: int = int(os.getenv("MAIL_PORT", 587))
    mail_server: str = os.getenv("MAIL_SERVER", "localhost")

    # إعدادات وسائل التواصل الاجتماعي
    facebook_access_token: Optional[str] = os.getenv("FACEBOOK_ACCESS_TOKEN")
    facebook_app_id: Optional[str] = os.getenv("FACEBOOK_APP_ID")
    facebook_app_secret: Optional[str] = os.getenv("FACEBOOK_APP_SECRET")
    twitter_api_key: Optional[str] = os.getenv("TWITTER_API_KEY")
    twitter_api_secret: Optional[str] = os.getenv("TWITTER_API_SECRET")
    twitter_access_token: Optional[str] = os.getenv("TWITTER_ACCESS_TOKEN")
    twitter_access_token_secret: Optional[str] = os.getenv("TWITTER_ACCESS_TOKEN_SECRET")

    # المتغيرات الإضافية
    huggingface_api_token: Optional[str] = os.getenv("HUGGINGFACE_API_TOKEN")
    refresh_secret_key: str = os.getenv("REFRESH_SECRET_KEY", "test_refresh_secret")
    default_language: str = os.getenv("DEFAULT_LANGUAGE", "ar")
    require_verified_for_community_creation: bool = _read_bool_env(
        "REQUIRE_VERIFIED_FOR_COMMUNITY_CREATION", False
    )
    MAX_OWNED_COMMUNITIES: int = int(os.getenv("MAX_OWNED_COMMUNITIES", 3))

    # إعدادات Firebase
    firebase_api_key: Optional[str] = os.getenv("FIREBASE_API_KEY")
    firebase_auth_domain: Optional[str] = os.getenv("FIREBASE_AUTH_DOMAIN")
    firebase_project_id: Optional[str] = os.getenv("FIREBASE_PROJECT_ID")
    firebase_storage_bucket: Optional[str] = os.getenv("FIREBASE_STORAGE_BUCKET")
    firebase_messaging_sender_id: Optional[str] = os.getenv("FIREBASE_MESSAGING_SENDER_ID")
    firebase_app_id: Optional[str] = os.getenv("FIREBASE_APP_ID")
    firebase_measurement_id: Optional[str] = os.getenv("FIREBASE_MEASUREMENT_ID")

    # إعدادات الإشعارات
    NOTIFICATION_RETENTION_DAYS: int = 90
    MAX_BULK_NOTIFICATIONS: int = 1000
    NOTIFICATION_QUEUE_TIMEOUT: int = 30
    NOTIFICATION_BATCH_SIZE: int = 100
    DEFAULT_NOTIFICATION_CHANNEL: str = "in_app"

    # إعدادات مفتاح RSA
    rsa_private_key_path: str = os.getenv(
        "RSA_PRIVATE_KEY_PATH", str(BASE_DIR / "private_key.pem")
    )
    rsa_public_key_path: str = os.getenv(
        "RSA_PUBLIC_KEY_PATH", str(BASE_DIR / "public_key.pem")
    )

    # إعدادات Redis وCelery
    REDIS_URL: Optional[str] = os.getenv("REDIS_URL")
    CELERY_BROKER_URL: str = os.getenv("CELERY_BROKER_URL", "redis://localhost:6379/0")
    CELERY_BACKEND_URL: str = os.getenv(
        "CELERY_BACKEND_URL", "redis://localhost:6379/0"
    )

    # تحميل المفاتيح
    _rsa_private_key: str = PrivateAttr()
    _rsa_public_key: str = PrivateAttr()

    # تعريف redis_client كمتغير فئة وليس كحقل بيانات
    redis_client: ClassVar[redis.Redis] = None

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        ignored_types=(redis.Redis,),
    )

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        # تحميل مفاتيح RSA في حال توفر المسارات
        self._rsa_private_key = self._read_key_file(
            self.rsa_private_key_path, "private"
        )
        self._rsa_public_key = self._read_key_file(self.rsa_public_key_path, "public")

        # إعداد Redis إذا كان REDIS_URL متاحًا
        if self.REDIS_URL:
            try:
                self.__class__.redis_client = redis.Redis.from_url(self.REDIS_URL)
                logger.info("Redis client successfully initialized.")
            except Exception as e:
                logger.error(f"Error connecting to Redis: {str(e)}")
                self.__class__.redis_client = None
        else:
            logger.warning(
                "REDIS_URL is not set, Redis client will not be initialized."
            )

    def _read_key_file(self, filename: Optional[str], key_type: str) -> str:
        if not filename:
            logger.warning(
                f"{key_type.capitalize()} key path is not provided; using empty key."
            )
            return ""
        if not os.path.exists(filename):
            logger.error(f"{key_type.capitalize()} key file not found: {filename}")
            return ""
        try:
            with open(filename, "r") as file:
                key_data = file.read().strip()
                if not key_data:
                    logger.error(
                        f"{key_type.capitalize()} key file is empty: {filename}"
                    )
                    return ""
                logger.info(f"Successfully read {key_type} key from {filename}")
                return key_data
        except IOError as e:
            logger.error(
                f"Error reading {key_type} key file: {filename}, error: {str(e)}"
            )
            return ""
        except Exception as e:
            logger.error(
                f"Unexpected error reading {key_type} key file: {filename}, error: {str(e)}"
            )
            return ""

    @property
    def rsa_private_key(self) -> str:
        return self._rsa_private_key

    @property
    def rsa_public_key(self) -> str:
        return self._rsa_public_key

    @property
    def mail_config(self) -> ConnectionConfig:
        config_data = {
            "MAIL_USERNAME": self.mail_username,
            "MAIL_PASSWORD": self.mail_password,
            "MAIL_FROM": self.mail_from,
            "MAIL_PORT": self.mail_port,
            "MAIL_SERVER": self.mail_server,
            "MAIL_FROM_NAME": "Your App Name",
            "MAIL_STARTTLS": True,
            "MAIL_SSL_TLS": False,
            "USE_CREDENTIALS": bool(self.mail_username and self.mail_password),
        }
        return CustomConnectionConfig(**config_data)

    @cached_property
    def database_url(self) -> str:
        """إرجاع رابط الاتصال بقاعدة البيانات مع استخدام قيم افتراضية آمنة للاختبار."""

        if self.database_url_override:
            return self.database_url_override

        required_values = [
            self.database_hostname,
            self.database_name,
            self.database_username,
            self.database_password,
        ]
        if all(required_values):
            port = self.database_port or "5432"
            password = self.database_password or ""
            return (
                f"postgresql://{self.database_username}:{password}"
                f"@{self.database_hostname}:{port}/{self.database_name}"
            )

        # القيمة الافتراضية للاختبارات والاستخدام المحلي
        return f"sqlite:///{BASE_DIR / 'app.db'}"


settings = Settings()

# إنشاء كائن FastMail ليُستخدم في إرسال الرسائل الإلكترونية
from fastapi_mail import FastMail

try:
    fm = FastMail(settings.mail_config)
except Exception as exc:
    logger.warning(f"FastMail initialization failed: {exc}")
    fm = None
