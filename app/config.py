import os
import logging
from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import EmailStr, PrivateAttr
from fastapi_mail import ConnectionConfig
import redis

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class Settings(BaseSettings):
    # AI and model configuration
    AI_MODEL_PATH: str = "bigscience/bloom-1b7"
    AI_MAX_LENGTH: int = 150
    AI_TEMPERATURE: float = 0.7

    # Database configuration
    database_hostname: str
    database_port: str
    database_password: str
    database_name: str
    database_username: str

    # Security settings
    secret_key: str
    algorithm: str = (
        ALGORITHM  # Ensure ALGORITHM is set in your environment or elsewhere
    )
    access_token_expire_minutes: int

    # Google OAuth settings
    google_client_id: str = "default_google_client_id"
    google_client_secret: str = "default_google_client_secret"

    # Email settings
    mail_username: str
    mail_password: str
    mail_from: EmailStr
    mail_port: int
    mail_server: str

    # Comment configuration
    COMMENT_EDIT_WINDOW_MINUTES: int = 15

    # Celery and Redis settings
    CELERY_BROKER_URL: str = REDIS_URL  # Ensure REDIS_URL is set in your environment
    HUGGINGFACE_API_TOKEN: str = (
        HUGGINGFACE_API_TOKEN  # Ensure HUGGINGFACE_API_TOKEN is set
    )
    REDIS_URL: str = REDIS_URL
    redis_client = redis.Redis.from_url(REDIS_URL)

    # Social media integrations
    facebook_access_token: str
    facebook_app_id: str
    facebook_app_secret: str
    twitter_api_key: str
    twitter_api_secret: str
    twitter_access_token: str
    twitter_access_token_secret: str

    # Additional integrations (commented out for now)
    # REDDIT_CLIENT_ID: str
    # REDDIT_CLIENT_SECRET: str
    # REDDIT_USER_AGENT: str = "YourApp/1.0"
    # LINKEDIN_CLIENT_ID: str
    # LINKEDIN_CLIENT_SECRET: str
    # LINKEDIN_REDIRECT_URI: str

    # Token refresh and language settings
    refresh_secret_key: str
    DEFAULT_LANGUAGE: str = "ar"

    # Firebase configuration
    firebase_api_key: str
    firebase_auth_domain: str
    firebase_project_id: str
    firebase_storage_bucket: str
    firebase_messaging_sender_id: str
    firebase_app_id: str
    firebase_measurement_id: str

    # Notification settings
    NOTIFICATION_RETENTION_DAYS: int = 90
    MAX_BULK_NOTIFICATIONS: int = 1000
    NOTIFICATION_QUEUE_TIMEOUT: int = 30
    NOTIFICATION_BATCH_SIZE: int = 100
    DEFAULT_NOTIFICATION_CHANNEL: str = "in_app"

    # RSA key file paths
    rsa_private_key_path: str
    rsa_public_key_path: str

    # Private attributes to hold RSA key contents
    _rsa_private_key: str = PrivateAttr()
    _rsa_public_key: str = PrivateAttr()

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")

    def __init__(self, **kwargs):
        """
        Initialize settings and read RSA keys from files.
        """
        super().__init__(**kwargs)
        self._rsa_private_key = self._read_key_file(
            self.rsa_private_key_path, "private"
        )
        self._rsa_public_key = self._read_key_file(self.rsa_public_key_path, "public")

    def _read_key_file(self, filename: str, key_type: str) -> str:
        """
        Read a key file and return its content as a string.

        Parameters:
            filename (str): Path to the key file.
            key_type (str): Type of the key ('private' or 'public').

        Raises:
            ValueError: If the file is not found, is empty, or cannot be read.
        """
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
        """
        Return the RSA private key content.
        """
        return self._rsa_private_key

    @property
    def rsa_public_key(self) -> str:
        """
        Return the RSA public key content.
        """
        return self._rsa_public_key

    @property
    def mail_config(self) -> ConnectionConfig:
        """
        Generate and return the email connection configuration for FastMail.
        """
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


# Instantiate the settings to be used throughout the application
settings = Settings()
