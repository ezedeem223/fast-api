import os
import logging
from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import EmailStr, PrivateAttr
from fastapi_mail import ConnectionConfig
import redis
from dotenv import load_dotenv

# تحميل متغيرات البيئة
load_dotenv()

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class Settings(BaseSettings):
    AI_MODEL_PATH: str = "bigscience/bloom-1b7"
    AI_MAX_LENGTH: int = 150
    AI_TEMPERATURE: float = 0.7

    # تحميل بيانات قاعدة البيانات من .env
    database_hostname: str = os.getenv("DATABASE_HOSTNAME")
    database_port: str = os.getenv("DATABASE_PORT")
    database_password: str = os.getenv("DATABASE_PASSWORD")
    database_name: str = os.getenv("DATABASE_NAME")
    database_username: str = os.getenv("DATABASE_USERNAME")

    secret_key: str = os.getenv("SECRET_KEY")
    algorithm: str = os.getenv("ALGORITHM")
    access_token_expire_minutes: int = int(os.getenv("ACCESS_TOKEN_EXPIRE_MINUTES", 30))

    google_client_id: str = os.getenv("GOOGLE_CLIENT_ID", "default_google_client_id")
    google_client_secret: str = os.getenv(
        "GOOGLE_CLIENT_SECRET", "default_google_client_secret"
    )

    mail_username: str = os.getenv("MAIL_USERNAME")
    mail_password: str = os.getenv("MAIL_PASSWORD")
    mail_from: EmailStr = os.getenv("MAIL_FROM")
    mail_port: int = int(os.getenv("MAIL_PORT"))
    mail_server: str = os.getenv("MAIL_SERVER")

    COMMENT_EDIT_WINDOW_MINUTES: int = 15
    CELERY_BROKER_URL: str = os.getenv("CELERY_BROKER_URL")
    HUGGINGFACE_API_TOKEN: str = os.getenv("HUGGINGFACE_API_TOKEN")

    REDIS_URL: str = os.getenv("REDIS_URL")
    redis_client = redis.Redis.from_url(REDIS_URL)

    facebook_access_token: str = os.getenv("FACEBOOK_ACCESS_TOKEN")
    facebook_app_id: str = os.getenv("FACEBOOK_APP_ID")
    facebook_app_secret: str = os.getenv("FACEBOOK_APP_SECRET")

    twitter_api_key: str = os.getenv("TWITTER_API_KEY")
    twitter_api_secret: str = os.getenv("TWITTER_API_SECRET")
    twitter_access_token: str = os.getenv("TWITTER_ACCESS_TOKEN")
    twitter_access_token_secret: str = os.getenv("TWITTER_ACCESS_TOKEN_SECRET")

    refresh_secret_key: str = os.getenv("REFRESH_SECRET_KEY")
    DEFAULT_LANGUAGE: str = os.getenv("DEFAULT_LANGUAGE", "ar")

    firebase_api_key: str = os.getenv("FIREBASE_API_KEY")
    firebase_auth_domain: str = os.getenv("FIREBASE_AUTH_DOMAIN")
    firebase_project_id: str = os.getenv("FIREBASE_PROJECT_ID")
    firebase_storage_bucket: str = os.getenv("FIREBASE_STORAGE_BUCKET")
    firebase_messaging_sender_id: str = os.getenv("FIREBASE_MESSAGING_SENDER_ID")
    firebase_app_id: str = os.getenv("FIREBASE_APP_ID")
    firebase_measurement_id: str = os.getenv("FIREBASE_MEASUREMENT_ID")

    rsa_private_key_path: str = os.getenv("RSA_PRIVATE_KEY_PATH")
    rsa_public_key_path: str = os.getenv("RSA_PUBLIC_KEY_PATH")

    _rsa_private_key: str = PrivateAttr()
    _rsa_public_key: str = PrivateAttr()

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self._rsa_private_key = self._read_key_file(
            self.rsa_private_key_path, "private"
        )
        self._rsa_public_key = self._read_key_file(self.rsa_public_key_path, "public")

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
        return ConnectionConfig(
            MAIL_USERNAME=self.mail_username,
            MAIL_PASSWORD=self.mail_password,
            MAIL_FROM=self.mail_from,
            MAIL_PORT=self.mail_port,
            MAIL_SERVER=self.mail_server,
            MAIL_FROM_NAME="Your App Name",
            MAIL_STARTTLS=True,
            MAIL_SSL_TLS=False,
            USE_CREDENTIALS=True,
        )


settings = Settings()

# REDDIT_CLIENT_ID: str
# REDDIT_CLIENT_SECRET: str
# REDDIT_USER_AGENT: str = "YourApp/1.0"
# LINKEDIN_CLIENT_ID: str
# LINKEDIN_CLIENT_SECRET: str
# LINKEDIN_REDIRECT_URI: str
