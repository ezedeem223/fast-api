import hvac
from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import EmailStr
import os

# إعداد اتصال بـ Vault
vault_token = os.getenv("VAULT_TOKEN")
client = hvac.Client(url="http://127.0.0.1:8200", token="vault_token")

# قراءة الأسرار من Vault
secret_data = client.secrets.kv.read_secret_version(path="fastapi")["data"]["data"]


class Settings(BaseSettings):
    database_hostname: str = secret_data["DATABASE_HOSTNAME"]
    database_port: str = secret_data["DATABASE_PORT"]
    database_password: str = secret_data["DATABASE_PASSWORD"]
    database_name: str = secret_data["DATABASE_NAME"]
    database_username: str = secret_data["DATABASE_USERNAME"]
    secret_key: str = secret_data["SECRET_KEY"]
    algorithm: str = secret_data["ALGORITHM"]
    access_token_expire_minutes: int = secret_data["ACCESS_TOKEN_EXPIRE_MINUTES"]
    mail_username: str = secret_data.get("MAIL_USERNAME", "default-email@example.com")
    mail_password: str = secret_data.get("MAIL_PASSWORD", "default-password")
    mail_from: EmailStr = secret_data.get("MAIL_FROM", "default-email@example.com")
    mail_port: int = secret_data.get("MAIL_PORT", 587)
    mail_server: str = secret_data.get("MAIL_SERVER", "smtp.example.com")

    # يمكن إضافة المزيد من المتغيرات حسب الحاجة

    model_config = SettingsConfigDict(env_file=".env")


settings = Settings()
