from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import EmailStr


class Settings(BaseSettings):
    database_hostname: str
    database_port: str
    database_password: str
    database_name: str
    database_username: str
    secret_key: str
    algorithm: str = "RS256"  # استخدم RS256 كخوارزمية التشفير
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

    # إضافة الخاصية المفقودة
    vault_token: str = "your_vault_token"

    rsa_private_key: str = "C:/Users/kglou/Desktop/fastapi/private_key.pem"
    rsa_public_key: str = "C:/Users/kglou/Desktop/fastapi/public_key.pem"

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"


settings = Settings()
