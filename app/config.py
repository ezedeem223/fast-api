import os
from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import EmailStr


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
    rsa_private_key_path: str = os.getenv(
        "RSA_PRIVATE_KEY_PATH", "/etc/secrets/private_key.pem"
    )
    rsa_public_key_path: str = os.getenv(
        "RSA_PUBLIC_KEY_PATH", "/etc/secrets/public_key.pem"
    )

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        # Print to verify values
        print(f"Mail Username: {self.mail_username}")
        print(f"Mail Password: {self.mail_password}")
        self.rsa_private_key = self._read_key_file(self.rsa_private_key_path)
        self.rsa_public_key = self._read_key_file(self.rsa_public_key_path)

    def _read_key_file(self, filename):
        try:
            with open(filename, "r") as file:
                return file.read().strip()
        except FileNotFoundError:
            raise ValueError(f"Key file not found: {filename}")


settings = Settings()
