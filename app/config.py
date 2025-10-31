import os
import logging
from pathlib import Path
from typing import ClassVar, Optional

import redis
from dotenv import load_dotenv
from fastapi_mail import ConnectionConfig, FastMail
from pydantic import EmailStr, PrivateAttr, ConfigDict
from pydantic_settings import BaseSettings, SettingsConfigDict

# ---------------------------------------------------------------------------
# Environment & logging setup
# ---------------------------------------------------------------------------
BASE_DIR = Path(__file__).resolve().parent.parent
DEFAULT_PRIVATE_KEY_PATH = BASE_DIR / "private_key.pem"
DEFAULT_PUBLIC_KEY_PATH = BASE_DIR / "public_key.pem"

load_dotenv()

# Remove FastAPI-Mail legacy flags that cause validation issues when unset.
os.environ.pop("MAIL_TLS", None)
os.environ.pop("MAIL_SSL", None)

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class CustomConnectionConfig(ConnectionConfig):
    """FastAPI-Mail configuration that tolerates extra fields."""

    model_config = ConfigDict(extra="ignore")


class Settings(BaseSettings):
    """Centralised application settings with sensible fallbacks.

    The historic project relied on a large collection of mandatory environment
    variables which made the application impossible to boot locally or in
    automated tests.  The new settings object provides defaults for optional
    integrations and gracefully degrades when credentials are missing.  This
    keeps the production configuration fully customisable while offering a
    predictable developer experience out of the box.
    """

    # ------------------------------------------------------------------
    # Core environment flags
    # ------------------------------------------------------------------
    environment: str = os.getenv("ENVIRONMENT", "development")
    testing: bool = os.getenv("TESTING", "0") in {"1", "true", "True"}
    enable_background_tasks: bool = (
        os.getenv("ENABLE_BACKGROUND_TASKS", "1") not in {"0", "false", "False"}
    )

    # ------------------------------------------------------------------
    # Database configuration
    # ------------------------------------------------------------------
    database_url: Optional[str] = os.getenv("DATABASE_URL")
    database_hostname: str = os.getenv("DATABASE_HOSTNAME", "localhost")
    database_port: str = os.getenv("DATABASE_PORT", "5432")
    database_password: str = os.getenv("DATABASE_PASSWORD", "password")
    database_name: str = os.getenv("DATABASE_NAME", "app")
    database_username: str = os.getenv("DATABASE_USERNAME", "postgres")

    # ------------------------------------------------------------------
    # Security
    # ------------------------------------------------------------------
    secret_key: str = os.getenv("SECRET_KEY", "change-me")
    refresh_secret_key: str = os.getenv("REFRESH_SECRET_KEY", "change-me-too")
    algorithm: str = os.getenv("ALGORITHM", "HS256")
    access_token_expire_minutes: int = int(os.getenv("ACCESS_TOKEN_EXPIRE_MINUTES", 30))

    # ------------------------------------------------------------------
    # Third-party integrations
    # ------------------------------------------------------------------
    google_client_id: str = os.getenv("GOOGLE_CLIENT_ID", "google-client-id")
    google_client_secret: str = os.getenv("GOOGLE_CLIENT_SECRET", "google-client-secret")
    facebook_access_token: str = os.getenv("FACEBOOK_ACCESS_TOKEN", "test-token")
    facebook_app_id: str = os.getenv("FACEBOOK_APP_ID", "test-app")
    facebook_app_secret: str = os.getenv("FACEBOOK_APP_SECRET", "test-secret")
    twitter_api_key: str = os.getenv("TWITTER_API_KEY", "twitter-key")
    twitter_api_secret: str = os.getenv("TWITTER_API_SECRET", "twitter-secret")
    twitter_access_token: str = os.getenv("TWITTER_ACCESS_TOKEN", "twitter-access")
    twitter_access_token_secret: str = os.getenv("TWITTER_ACCESS_TOKEN_SECRET", "twitter-access-secret")
    huggingface_api_token: str = os.getenv("HUGGINGFACE_API_TOKEN", "")

    # ------------------------------------------------------------------
    # Email
    # ------------------------------------------------------------------
    mail_username: str = os.getenv("MAIL_USERNAME", "noreply@example.com")
    mail_password: str = os.getenv("MAIL_PASSWORD", "password")
    mail_from: EmailStr = "noreply@example.com"
    mail_port: int = int(os.getenv("MAIL_PORT", 587))
    mail_server: str = os.getenv("MAIL_SERVER", "localhost")

    # ------------------------------------------------------------------
    # Firebase
    # ------------------------------------------------------------------
    firebase_api_key: str = os.getenv("FIREBASE_API_KEY", "firebase-api-key")
    firebase_auth_domain: str = os.getenv("FIREBASE_AUTH_DOMAIN", "firebase-app.firebaseapp.com")
    firebase_project_id: str = os.getenv("FIREBASE_PROJECT_ID", "firebase-project")
    firebase_storage_bucket: str = os.getenv("FIREBASE_STORAGE_BUCKET", "firebase-bucket")
    firebase_messaging_sender_id: str = os.getenv("FIREBASE_MESSAGING_SENDER_ID", "1234567890")
    firebase_app_id: str = os.getenv("FIREBASE_APP_ID", "firebase-app")
    firebase_measurement_id: str = os.getenv("FIREBASE_MEASUREMENT_ID", "G-TEST")

    # ------------------------------------------------------------------
    # Localisation & defaults
    # ------------------------------------------------------------------
    default_language: str = os.getenv("DEFAULT_LANGUAGE", "ar")

    # ------------------------------------------------------------------
    # Notifications
    # ------------------------------------------------------------------
    NOTIFICATION_RETENTION_DAYS: int = 90
    MAX_BULK_NOTIFICATIONS: int = 1000
    NOTIFICATION_QUEUE_TIMEOUT: int = 30
    NOTIFICATION_BATCH_SIZE: int = 100
    DEFAULT_NOTIFICATION_CHANNEL: str = "in_app"

    # ------------------------------------------------------------------
    # Redis / Celery
    # ------------------------------------------------------------------
    REDIS_URL: Optional[str] = os.getenv("REDIS_URL")
    CELERY_BROKER_URL: str = os.getenv("CELERY_BROKER_URL", "redis://localhost:6379/0")
    CELERY_BACKEND_URL: str = os.getenv("CELERY_BACKEND_URL", "redis://localhost:6379/0")

    # ------------------------------------------------------------------
    # RSA keys & mail configuration
    # ------------------------------------------------------------------
    rsa_private_key_path: Optional[str] = os.getenv("RSA_PRIVATE_KEY_PATH", str(DEFAULT_PRIVATE_KEY_PATH))
    rsa_public_key_path: Optional[str] = os.getenv("RSA_PUBLIC_KEY_PATH", str(DEFAULT_PUBLIC_KEY_PATH))

    # Internal caches
    _rsa_private_key: str = PrivateAttr()
    _rsa_public_key: str = PrivateAttr()

    redis_client: ClassVar[Optional[redis.Redis]] = None

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        ignored_types=(redis.Redis,),
    )

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self._rsa_private_key = self._read_key_file(self.rsa_private_key_path, "private")
        self._rsa_public_key = self._read_key_file(self.rsa_public_key_path, "public")

        if self.REDIS_URL:
            try:
                self.__class__.redis_client = redis.Redis.from_url(self.REDIS_URL)
                logger.info("Redis client successfully initialized.")
            except Exception as exc:  # pragma: no cover - defensive logging
                logger.error("Error connecting to Redis: %s", exc)
                self.__class__.redis_client = None
        else:
            logger.info("REDIS_URL is not set; Redis features are disabled.")

    # ------------------------------------------------------------------
    # Derived properties
    # ------------------------------------------------------------------
    @property
    def sqlalchemy_database_uri(self) -> str:
        """Return a fully qualified SQLAlchemy connection string.

        Preference order:
        1. Explicit DATABASE_URL.
        2. Classic Postgres credentials.
        3. Local SQLite database for development/testing.
        """

        if self.database_url:
            return self.database_url

        required = [self.database_hostname, self.database_name, self.database_username]
        if all(required):
            return (
                "postgresql://"
                f"{self.database_username}:{self.database_password}"
                f"@{self.database_hostname}:{self.database_port}/{self.database_name}"
            )

        sqlite_path = BASE_DIR / "app.db"
        return f"sqlite:///{sqlite_path.as_posix()}"

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

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------
    def _read_key_file(self, filename: Optional[str], key_type: str) -> str:
        if not filename:
            logger.warning("No %s key path provided; using generated placeholder.", key_type)
            return self._generate_in_memory_key(key_type)

        path = Path(filename)
        if not path.is_absolute():
            path = BASE_DIR / path

        if not path.exists():
            logger.warning("%s key file not found at %s; using in-memory fallback.", key_type.capitalize(), path)
            return self._generate_in_memory_key(key_type)

        try:
            key_data = path.read_text(encoding="utf-8").strip()
        except OSError as exc:  # pragma: no cover - defensive logging
            logger.error("Error reading %s key file %s: %s", key_type, path, exc)
            raise ValueError(f"Error reading {key_type} key file: {path}") from exc

        if not key_data:
            logger.warning("%s key file at %s is empty; using in-memory fallback.", key_type.capitalize(), path)
            return self._generate_in_memory_key(key_type)

        logger.info("Successfully read %s key from %s", key_type, path)
        return key_data

    def _generate_in_memory_key(self, key_type: str) -> str:
        placeholder = (
            "-----BEGIN RSA {type} KEY-----\n"
            "MIIBOgIBAAJBAL0n9fBx8r1u4qScT8QJADH3Jbf4zX0JZVNsBnm0nX6kLEuZF8oF\n"
            "T2qz4j0Qm4RUSO3lO9A6r5Z0iLuW9R4EEl0CAwEAAQJAB7Q+v4u+RyUNmWQ54uQJ\n"
            "hG7Y7nN5rTzB0B7G/3AcvTjgkfv+2w9KOiQmU4xGsm6NnE7gW40zXQjG5n0gFe5Q\n"
            "AQIhAPsb1lO4E4mYy6Jp3mV6l9xB7JpeuN5DuJc2s7MH7B2DAiEAxJvG5p0Swiz6\n"
            "e2X9oChtYpKAz9S41E9XgYq6Dz+cGgMCIQD7N9WfwXK4nQbh/Kwcz6pXw6TYtAxJ\n"
            "6Y6OH9quGBkdjQIhAK5wSK8rwM5BJxR0QYFna4Z3Ywguq2iYQ4XK4iWxGgMlAiEA\n"
            "sx6nJb8V6m0zSqfY9L6YrA2hS1l9rxzu9YaAjwDlMyY=\n"
            "-----END RSA {type} KEY-----"
        )
        return placeholder.format(type=key_type.upper())


settings = Settings()

fm = FastMail(settings.mail_config)
