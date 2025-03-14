import os
import logging
from typing import ClassVar
from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import EmailStr, PrivateAttr, Extra
from fastapi_mail import ConnectionConfig, FastMail
import redis
from fastapi_mail import FastMail  # للتذكير نستخدمه لاحقًا

# تحميل ملف .env (مفيد للتطوير محلياً)
from dotenv import load_dotenv

load_dotenv()

# إزالة المتغيرات البيئية غير المطلوبة لتفادي أخطاء التحقق
os.environ.pop("MAIL_TLS", None)
os.environ.pop("MAIL_SSL", None)

# إعدادات تسجيل الأخطاء
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


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
    DATABASE_HOSTNAME: str
    DATABASE_PORT: int
    DATABASE_PASSWORD: str
    DATABASE_NAME: str
    DATABASE_USERNAME: str

    # إعدادات الأمان
    SECRET_KEY: str
    ALGORITHM: str
    ACCESS_TOKEN_EXPIRE_MINUTES: int

    # إعدادات خدمات الجهات الخارجية
    GOOGLE_CLIENT_ID: str = "your_google_client_id"
    GOOGLE_CLIENT_SECRET: str = "your_google_client_secret"
    FACEBOOK_ACCESS_TOKEN: str
    FACEBOOK_APP_ID: str
    FACEBOOK_APP_SECRET: str

    # إعدادات البريد الإلكتروني
    MAIL_USERNAME: EmailStr
    MAIL_PASSWORD: str
    MAIL_FROM: EmailStr
    MAIL_PORT: int = 587
    MAIL_SERVER: str

    # إعدادات وسائل التواصل الاجتماعي (تويتر)
    TWITTER_API_KEY: str
    TWITTER_API_SECRET: str
    TWITTER_ACCESS_TOKEN: str
    TWITTER_ACCESS_TOKEN_SECRET: str

    # إعدادات إضافية
    HUGGINGFACE_API_TOKEN: str
    REFRESH_SECRET_KEY: str
    DEFAULT_LANGUAGE: str = "ar"

    # إعدادات Firebase
    FIREBASE_API_KEY: str
    FIREBASE_AUTH_DOMAIN: str
    FIREBASE_PROJECT_ID: str
    FIREBASE_STORAGE_BUCKET: str
    FIREBASE_MESSAGING_SENDER_ID: str
    FIREBASE_APP_ID: str
    FIREBASE_MEASUREMENT_ID: str

    # إعدادات RSA
    RSA_PRIVATE_KEY_PATH: str
    RSA_PUBLIC_KEY_PATH: str

    # إعدادات Redis وCelery
    REDIS_URL: str
    CELERY_BROKER_URL: str = "redis://localhost:6379/0"
    CELERY_BACKEND_URL: str = "redis://localhost:6379/0"

    # المتغيرات الخاصة لمفاتيح RSA (لن تُعرض كحقول)
    _rsa_private_key: str = PrivateAttr()
    _rsa_public_key: str = PrivateAttr()

    # تعريف عميل Redis كمتغير فئة
    redis_client: ClassVar[redis.Redis] = None

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        ignored_types=(redis.Redis,),
    )

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        # تحميل مفاتيح RSA من الملفات
        self._rsa_private_key = self._read_key_file(
            self.RSA_PRIVATE_KEY_PATH, "private"
        )
        self._rsa_public_key = self._read_key_file(self.RSA_PUBLIC_KEY_PATH, "public")

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

    def _read_key_file(self, filename: str, key_type: str) -> str:
        if not os.path.exists(filename):
            logger.error(f"{key_type.capitalize()} key file not found: {filename}")
            raise ValueError(f"{key_type.capitalize()} key file not found: {filename}")
        try:
            with open(filename, "r") as file:
                key_data = file.read().strip()
                if not key_data:
                    logger.error(
                        f"{key_type.capitalize()} key file is empty: {filename}"
                    )
                    raise ValueError(
                        f"{key_type.capitalize()} key file is empty: {filename}"
                    )
                logger.info(f"Successfully read {key_type} key from {filename}")
                return key_data
        except IOError as e:
            logger.error(
                f"Error reading {key_type} key file: {filename}, error: {str(e)}"
            )
            raise ValueError(
                f"Error reading {key_type} key file: {filename}, error: {str(e)}"
            )
        except Exception as e:
            logger.error(
                f"Unexpected error reading {key_type} key file: {filename}, error: {str(e)}"
            )
            raise ValueError(
                f"Unexpected error reading {key_type} key file: {filename}, error: {str(e)}"
            )

    @property
    def rsa_private_key(self) -> str:
        return self._rsa_private_key

    @property
    def rsa_public_key(self) -> str:
        return self._rsa_public_key

    @property
    def mail_config(self) -> ConnectionConfig:
        config_data = {
            "MAIL_USERNAME": self.MAIL_USERNAME,
            "MAIL_PASSWORD": self.MAIL_PASSWORD,
            "MAIL_FROM": self.MAIL_FROM,
            "MAIL_PORT": self.MAIL_PORT,
            "MAIL_SERVER": self.MAIL_SERVER,
            "MAIL_FROM_NAME": "Your App Name",
            "MAIL_STARTTLS": True,
            "MAIL_SSL_TLS": False,
            "USE_CREDENTIALS": True,
        }
        return CustomConnectionConfig(**config_data)


# إنشاء كائن الإعدادات ليُستخدم في باقي التطبيق
settings = Settings()

# إنشاء كائن FastMail لإرسال الرسائل الإلكترونية
fm = FastMail(settings.mail_config)
