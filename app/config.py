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
    vault_token: str = "your_vault_token"
    rsa_private_key: str
    rsa_public_key: str

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.rsa_private_key = self._read_key_file("private_key.pem")
        self.rsa_public_key = self._read_key_file("public_key.pem")

    def _read_key_file(self, filename):
        file_path = os.path.join(os.path.dirname(__file__), "..", filename)
        try:
            with open(file_path, "r") as file:
                return file.read().strip()
        except FileNotFoundError:
            raise ValueError(f"Key file not found: {filename}")


settings = Settings()
