import os
import logging
from pathlib import Path
from typing import ClassVar, Optional

import redis
from dotenv import load_dotenv
from fastapi_mail import ConnectionConfig
from pydantic import EmailStr, PrivateAttr, ConfigDict
from pydantic_settings import BaseSettings, SettingsConfigDict

# Base directory of the project; used for resolving relative paths reliably.
# (__file__ is app/core/config/settings.py, so we need to traverse three levels up)
BASE_DIR = Path(__file__).resolve().parents[3]


# طھط­ظ…ظٹظ„ ظ…ظ„ظپ .env
load_dotenv(BASE_DIR / ".env")

# ط¥ط²ط§ظ„ط© ط§ظ„ظ…طھط؛ظٹط±ط§طھ ط§ظ„ط¨ظٹط¦ظٹط© ط؛ظٹط± ط§ظ„ظ…ط·ظ„ظˆط¨ط© ظ„طھظپط§ط¯ظٹ ط£ط®ط·ط§ط، ط§ظ„طھط­ظ‚ظ‚
os.environ.pop("MAIL_TLS", None)
os.environ.pop("MAIL_SSL", None)

# ط¥ط¹ط¯ط§ط¯ط§طھ طھط³ط¬ظٹظ„ ط§ظ„ط£ط®ط·ط§ط،
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


# ط¥ظ†ط´ط§ط، طµظ†ظپ ظ…ط®طµطµ ظ„طھط¹ط·ظٹظ„ ط§ظ„طھط­ظ‚ظ‚ ظ…ظ† ط§ظ„ط­ظ‚ظˆظ„ ط§ظ„ط¥ط¶ط§ظپظٹط© ظپظٹ ط¥ط¹ط¯ط§ط¯ط§طھ ط§ظ„ط¨ط±ظٹط¯ ط§ظ„ط¥ظ„ظƒطھط±ظˆظ†ظٹ
class CustomConnectionConfig(ConnectionConfig):
    model_config = ConfigDict(extra="ignore")


class Settings(BaseSettings):
    """Application configuration loaded from environment variables."""

    model_config: ClassVar[SettingsConfigDict] = SettingsConfigDict(
        env_file=str(BASE_DIR / ".env"),
        env_file_encoding="utf-8",
        extra="ignore",
        ignored_types=(redis.Redis,),
    )
    # ط¥ط¹ط¯ط§ط¯ط§طھ ط§ظ„ط°ظƒط§ط، ط§ظ„ط§طµط·ظ†ط§ط¹ظٹ
    AI_MODEL_PATH: str = "bigscience/bloom-1b7"
    AI_MAX_LENGTH: int = 150
    AI_TEMPERATURE: float = 0.7

    # ط¥ط¹ط¯ط§ط¯ط§طھ ظ‚ط§ط¹ط¯ط© ط§ظ„ط¨ظٹط§ظ†ط§طھ
    database_url: Optional[str] = os.getenv("DATABASE_URL")
    test_database_url: str = os.getenv("TEST_DATABASE_URL", "sqlite:///./test.db")
    database_hostname: Optional[str] = os.getenv("DATABASE_HOSTNAME")
    database_port: str = os.getenv("DATABASE_PORT", "5432")
    database_password: Optional[str] = os.getenv("DATABASE_PASSWORD")
    database_name: Optional[str] = os.getenv("DATABASE_NAME")
    database_username: Optional[str] = os.getenv("DATABASE_USERNAME")
    database_ssl_mode: str = os.getenv("DATABASE_SSL_MODE", "require")
    environment: str = os.getenv('APP_ENV', 'production')
    MAX_OWNED_COMMUNITIES: int = int(os.getenv("MAX_OWNED_COMMUNITIES", 5))

    # ط¥ط¹ط¯ط§ط¯ط§طھ ط§ظ„ط£ظ…ط§ظ†
    secret_key: str = os.getenv("SECRET_KEY")
    algorithm: str = os.getenv("ALGORITHM")
    access_token_expire_minutes: int = int(os.getenv("ACCESS_TOKEN_EXPIRE_MINUTES", 30))

    # ط¥ط¹ط¯ط§ط¯ط§طھ ط®ط¯ظ…ط§طھ ط§ظ„ط¬ظ‡ط§طھ ط§ظ„ط®ط§ط±ط¬ظٹط©
    google_client_id: str = os.getenv("GOOGLE_CLIENT_ID", "default_google_client_id")
    google_client_secret: str = os.getenv(
        "GOOGLE_CLIENT_SECRET", "default_google_client_secret"
    )
    # REDDIT_CLIENT_ID: str = os.getenv("REDDIT_CLIENT_ID", "default_reddit_client_id")
    # REDDIT_CLIENT_SECRET: str = os.getenv("REDDIT_CLIENT_SECRET", "default_reddit_client_secret")

    # ط¥ط¹ط¯ط§ط¯ط§طھ ط§ظ„ط¨ط±ظٹط¯ ط§ظ„ط¥ظ„ظƒطھط±ظˆظ†ظٹ
    mail_username: str = os.getenv("MAIL_USERNAME")
    mail_password: str = os.getenv("MAIL_PASSWORD")
    mail_from: EmailStr = os.getenv("MAIL_FROM")
    mail_port: int = int(os.getenv("MAIL_PORT", 587))
    mail_server: str = os.getenv("MAIL_SERVER")

    # ط¥ط¹ط¯ط§ط¯ط§طھ ظˆط³ط§ط¦ظ„ ط§ظ„طھظˆط§طµظ„ ط§ظ„ط§ط¬طھظ…ط§ط¹ظٹ
    facebook_access_token: str = os.getenv("FACEBOOK_ACCESS_TOKEN")
    facebook_app_id: str = os.getenv("FACEBOOK_APP_ID")
    facebook_app_secret: str = os.getenv("FACEBOOK_APP_SECRET")
    twitter_api_key: str = os.getenv("TWITTER_API_KEY")
    twitter_api_secret: str = os.getenv("TWITTER_API_SECRET")
    twitter_access_token: str = os.getenv("TWITTER_ACCESS_TOKEN")
    twitter_access_token_secret: str = os.getenv("TWITTER_ACCESS_TOKEN_SECRET")

    # ط§ظ„ظ…طھط؛ظٹط±ط§طھ ط§ظ„ط¥ط¶ط§ظپظٹط©
    huggingface_api_token: str = os.getenv("HUGGINGFACE_API_TOKEN")
    refresh_secret_key: str = os.getenv("REFRESH_SECRET_KEY")
    default_language: str = os.getenv("DEFAULT_LANGUAGE", "ar")

    # ط¥ط¹ط¯ط§ط¯ط§طھ Firebase
    firebase_api_key: str = os.getenv("FIREBASE_API_KEY")
    firebase_auth_domain: str = os.getenv("FIREBASE_AUTH_DOMAIN")
    firebase_project_id: str = os.getenv("FIREBASE_PROJECT_ID")
    firebase_storage_bucket: str = os.getenv("FIREBASE_STORAGE_BUCKET")
    firebase_messaging_sender_id: str = os.getenv("FIREBASE_MESSAGING_SENDER_ID")
    firebase_app_id: str = os.getenv("FIREBASE_APP_ID")
    firebase_measurement_id: str = os.getenv("FIREBASE_MEASUREMENT_ID")

    # ط¥ط¹ط¯ط§ط¯ط§طھ ط§ظ„ط¥ط´ط¹ط§ط±ط§طھ
    NOTIFICATION_RETENTION_DAYS: int = 90
    MAX_BULK_NOTIFICATIONS: int = 1000
    NOTIFICATION_QUEUE_TIMEOUT: int = 30
    NOTIFICATION_BATCH_SIZE: int = 100
    DEFAULT_NOTIFICATION_CHANNEL: str = "in_app"

    # ط¥ط¹ط¯ط§ط¯ط§طھ ظ…ظپطھط§ط­ RSA
    rsa_private_key_path: str = os.getenv(
        "RSA_PRIVATE_KEY_PATH", str(BASE_DIR / "private_key.pem")
    )
    rsa_public_key_path: str = os.getenv(
        "RSA_PUBLIC_KEY_PATH", str(BASE_DIR / "public_key.pem")
    )

    # ط¥ط¹ط¯ط§ط¯ط§طھ Redis ظˆCelery
    REDIS_URL: str = os.getenv("REDIS_URL")
    CELERY_BROKER_URL: str = os.getenv("CELERY_BROKER_URL", "redis://localhost:6379/0")
    CELERY_BACKEND_URL: str = os.getenv(
        "CELERY_BACKEND_URL", "redis://localhost:6379/0"
    )

    # طھط­ظ…ظٹظ„ ط§ظ„ظ…ظپط§طھظٹط­
    _rsa_private_key: str = PrivateAttr()
    _rsa_public_key: str = PrivateAttr()

    # طھط¹ط±ظٹظپ redis_client ظƒظ…طھط؛ظٹط± ظپط¦ط© ظˆظ„ظٹط³ ظƒط­ظ‚ظ„ ط¨ظٹط§ظ†ط§طھ
    redis_client: ClassVar[redis.Redis] = None

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        # طھط­ظ…ظٹظ„ ظ…ظپط§طھظٹط­ RSA
        self._rsa_private_key = self._read_key_file(
            self.rsa_private_key_path, "private"
        )
        self._rsa_public_key = self._read_key_file(self.rsa_public_key_path, "public")

        # ط¥ط¹ط¯ط§ط¯ Redis ط¥ط°ط§ ظƒط§ظ† REDIS_URL ظ…طھط§ط­ظ‹ط§
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

    def get_database_url(self, *, use_test: bool = False) -> str:
        """
        Resolve the SQLAlchemy database URL for runtime or tests.
        """
        if use_test and self.test_database_url:
            return self.test_database_url

        if self.database_url:
            return self.database_url

        if (
            self.database_hostname
            and self.database_username
            and self.database_password
            and self.database_name
        ):
            base_url = (
                f"postgresql+psycopg2://{self.database_username}:{self.database_password}"
                f"@{self.database_hostname}:{self.database_port}/{self.database_name}"
            )
            if self.database_ssl_mode:
                return f"{base_url}?sslmode={self.database_ssl_mode}"
            return base_url

        if self.test_database_url:
            return self.test_database_url

        raise ValueError(
            "Database configuration is incomplete; please set DATABASE_URL or the individual components."
        )

    def _read_key_file(self, filename: str, key_type: str) -> str:
        if not filename:
            logger.error(f"{key_type.capitalize()} key file path is not provided.")
            raise ValueError(f"{key_type.capitalize()} key file path is not provided.")

        candidate_paths = []
        raw_path = Path(filename)
        if not raw_path.is_absolute():
            candidate_paths.append((BASE_DIR / raw_path).resolve())
        candidate_paths.append(raw_path.resolve())

        file_path: Optional[Path] = next(
            (path for path in candidate_paths if path.exists()), None
        )

        if not file_path:
            logger.error(f"{key_type.capitalize()} key file not found: {filename}")
            raise ValueError(f"{key_type.capitalize()} key file not found: {filename}")
        try:
            with file_path.open("r", encoding="utf-8") as file:
                key_data = file.read().strip()
                if not key_data:
                    logger.error(
                        f"{key_type.capitalize()} key file is empty: {file_path}"
                    )
                    raise ValueError(
                        f"{key_type.capitalize()} key file is empty: {file_path}"
                    )
                logger.info(f"Successfully read {key_type} key from {file_path}")
                return key_data
        except IOError as e:
            logger.error(
                f"Error reading {key_type} key file: {file_path}, error: {str(e)}"
            )
            raise ValueError(
                f"Error reading {key_type} key file: {file_path}, error: {str(e)}"
            )
        except Exception as e:
            logger.error(
                f"Unexpected error reading {key_type} key file: {file_path}, error: {str(e)}"
            )
            raise ValueError(
                f"Unexpected error reading {key_type} key file: {file_path}, error: {str(e)}"
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
            "MAIL_USERNAME": self.mail_username,
            "MAIL_PASSWORD": self.mail_password,
            "MAIL_FROM": self.mail_from,
            "MAIL_PORT": self.mail_port,
            "MAIL_SERVER": self.mail_server,
            "MAIL_FROM_NAME": "Your App Name",
            "MAIL_STARTTLS": True,
            "MAIL_SSL_TLS": False,
            "USE_CREDENTIALS": True,
        }
        return CustomConnectionConfig(**config_data)



# ط¥ظ†ط´ط§ط، ظƒط§ط¦ظ† FastMail ظ„ظٹظڈط³طھط®ط¯ظ… ظپظٹ ط¥ط±ط³ط§ظ„ ط§ظ„ط±ط³ط§ط¦ظ„ ط§ظ„ط¥ظ„ظƒطھط±ظˆظ†ظٹط©

