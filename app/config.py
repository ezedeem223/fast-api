import os
import logging
from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import EmailStr, PrivateAttr
from fastapi_mail import ConnectionConfig

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class Settings(BaseSettings):
    database_hostname: str
    database_port: str
    database_password: str
    database_name: str
    database_username: str
    secret_key: str
    algorithm: str = "RS256"
    access_token_expire_minutes: int
    google_client_id: str = "default_google_client_id"
    google_client_secret: str = "default_google_client_secret"
    facebook_client_id: str = "default_facebook_client_id"
    facebook_client_secret: str = "default_facebook_client_secret"
    mail_username: str
    mail_password: str
    mail_from: EmailStr
    mail_port: int
    mail_server: str
    COMMENT_EDIT_WINDOW_MINUTES: int = 15
    # # أضف الحقول الجديدة هنا
    # facebook_access_token: "default_facebook_client_secret"
    # facebook_app_id: "default_facebook_client_secret"
    # facebook_app_secret: "default_facebook_client_secret"
    # twitter_api_key: "default_facebook_client_secret"
    # twitter_api_secret: "default_facebook_client_secret"
    # twitter_access_token: "default_facebook_client_secret"
    # twitter_access_token_secret: "default_facebook_client_secret"

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
