import os
import logging
from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import EmailStr, PrivateAttr
from fastapi_mail import ConnectionConfig
import redis

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class Settings(BaseSettings):
    database_hostname: str
    database_port: str
    database_password: str
    database_name: str
    database_username: str
    secret_key: str
    algorithm: str = ALGORITHM
    access_token_expire_minutes: int
    google_client_id: str = "default_google_client_id"
    google_client_secret: str = "default_google_client_secret"
    mail_username: str
    mail_password: str
    mail_from: EmailStr
    mail_port: int
    mail_server: str
    COMMENT_EDIT_WINDOW_MINUTES: int = 15
    CELERY_BROKER_URL: str = REDIS_URL
    HUGGINGFACE_API_TOKEN: str = HUGGINGFACE_API_TOKEN
    REDIS_URL = REDIS_URL
    redis_client = redis.Redis.from_url(REDIS_URL)
    facebook_access_token: str
    facebook_app_id: str
    facebook_app_secret: str
    twitter_api_key: str
    twitter_api_secret: str
    twitter_access_token: str
    twitter_access_token_secret: str
    refresh_secret_key: str
    DEFAULT_LANGUAGE = "ar"
    firebase_api_key: str
    firebase_auth_domain: str
    firebase_project_id: str
    firebase_storage_bucket: str
    firebase_messaging_sender_id: str
    firebase_app_id: str
    firebase_measurement_id: str
    NOTIFICATION_RETENTION_DAYS: int = 90
    MAX_BULK_NOTIFICATIONS: int = 1000
    NOTIFICATION_QUEUE_TIMEOUT: int = 30
    NOTIFICATION_BATCH_SIZE: int = 100
    DEFAULT_NOTIFICATION_CHANNEL: str = "in_app"

    rsa_private_key_path: str
    rsa_public_key_path: str

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
