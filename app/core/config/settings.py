"""Application settings loaded from environment with safe fallbacks and keyfile validation.

Environment precedence:
- Loads `.env` from the repo root before reading process env vars.
- Most values are pulled straight from env; booleans go through `_env_flag` so `"0"/"false"` work.
- CORS is normalized from `CORS_ORIGINS` (comma-separated) with a conservative default allowlist.
- RSA keys are resolved relative to the repo root when given relative paths and must be non-empty.
- Redis is optional: failure to connect logs an error but keeps the app running.

Key expectations (defaults in parentheses):
- `APP_ENV` controls settings class selection (`production` default).
- Database: `DATABASE_URL` or component parts (`DATABASE_*`), with `_test` suffix enforced in tests.
- Redis: `REDIS_URL` enables cache; absence keeps cache disabled without failing startup.
- TLS/hosts: `ALLOWED_HOSTS` (JSON or comma list), `FORCE_HTTPS` (true in production if unset).
- Crypto: `RSA_PRIVATE_KEY_PATH` / `RSA_PUBLIC_KEY_PATH` (repo-relative if not absolute).
- Mail: credentials optional; defaults to empty values in tests/CI; TLS flags removed to avoid dotenv quirks.
"""

import json
import logging
import os
from pathlib import Path
from typing import Any, ClassVar, Optional

import redis
from dotenv import load_dotenv
from fastapi_mail import ConnectionConfig
from pydantic import ConfigDict, EmailStr, PrivateAttr
from pydantic_settings import BaseSettings, SettingsConfigDict

# Base directory of the project; used for resolving relative paths reliably.
# (__file__ is app/core/config/settings.py, so we need to traverse three levels up)
BASE_DIR = Path(__file__).resolve().parents[3]


load_dotenv(BASE_DIR / ".env")

# fastapi-mail treats presence of these flags as truthy; remove to rely on explicit config below.
os.environ.pop("MAIL_TLS", None)
os.environ.pop("MAIL_SSL", None)

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def _env_flag(name: str, *, default: Optional[bool] = False) -> Optional[bool]:
    """
    Helper to parse boolean-like environment variables.
    """
    value = os.getenv(name)
    if value is None:
        return default
    return value.lower() in {"1", "true", "yes", "on"}


class CustomConnectionConfig(ConnectionConfig):
    """FastMail config that ignores extra fields to tolerate lenient env mapping."""

    model_config = ConfigDict(extra="ignore")


class Settings(BaseSettings):
    """Application configuration loaded from environment variables.

    Behavior highlights:
    - Loads `.env` at repo root, then lets process env override.
    - Enforces safe DB URLs (prefers `DATABASE_URL`, ensures `_test` suffix for test DBs).
    - Feature toggles parsed via `_env_flag` to accept common truthy/falsey strings.
    - Redis optional: failures disable caching but do not stop startup.
    - RSA keys resolved relative to repo root when not absolute; empty/missing files raise early errors.
    - CORS/hosts normalized once to avoid mutation side effects in settings instances.
    """

    model_config: ClassVar[SettingsConfigDict] = SettingsConfigDict(
        env_file=str(BASE_DIR / ".env"),
        env_file_encoding="utf-8",
        extra="ignore",
        ignored_types=(redis.Redis,),
    )
    AI_MODEL_PATH: str = "bigscience/bloom-1b7"
    AI_MAX_LENGTH: int = 150
    AI_TEMPERATURE: float = 0.7

    database_url: Optional[str] = os.getenv("DATABASE_URL")
    test_database_url: Optional[str] = os.getenv("TEST_DATABASE_URL")
    database_hostname: Optional[str] = os.getenv("DATABASE_HOSTNAME")
    database_port: str = os.getenv("DATABASE_PORT", "5432")
    database_password: Optional[str] = os.getenv("DATABASE_PASSWORD")
    database_name: Optional[str] = os.getenv("DATABASE_NAME")
    database_username: Optional[str] = os.getenv("DATABASE_USERNAME")
    database_ssl_mode: str = os.getenv("DATABASE_SSL_MODE", "require")
    environment: str = os.getenv("APP_ENV", "production")
    force_https: bool = False
    log_level: str = os.getenv("LOG_LEVEL", "INFO")
    log_dir: str = os.getenv("LOG_DIR", "logs")
    use_json_logs: bool = _env_flag("USE_JSON_LOGS", default=True)
    otel_exporter_otlp_endpoint: Optional[str] = os.getenv(
        "OTEL_EXPORTER_OTLP_ENDPOINT"
    )
    otel_enabled: Optional[bool] = _env_flag("OTEL_ENABLED", default=None)
    sentry_dsn: Optional[str] = os.getenv("SENTRY_DSN")
    sentry_traces_sample_rate: float = float(
        os.getenv("SENTRY_TRACES_SAMPLE_RATE", "0.1")
    )
    # Accept raw string from env to avoid JSON parse errors; we normalize to list in __init__
    allowed_hosts: Optional[str] = os.getenv("ALLOWED_HOSTS")
    cors_origins: list[str] = []
    MAX_OWNED_COMMUNITIES: int = int(os.getenv("MAX_OWNED_COMMUNITIES", 5))
    MAX_PENDING_INVITATIONS: int = int(os.getenv("MAX_PENDING_INVITATIONS", 50))
    INVITATION_EXPIRY_DAYS: int = int(os.getenv("INVITATION_EXPIRY_DAYS", 14))
    BASE_URL: str = os.getenv("BASE_URL", "http://localhost:8000")
    SITE_NAME: str = os.getenv("SITE_NAME", "FastAPI Platform")

    secret_key: str = os.getenv("SECRET_KEY")
    algorithm: str = os.getenv("ALGORITHM")
    access_token_expire_minutes: int = int(os.getenv("ACCESS_TOKEN_EXPIRE_MINUTES", 30))

    google_client_id: str = os.getenv("GOOGLE_CLIENT_ID", "default_google_client_id")
    google_client_secret: str = os.getenv(
        "GOOGLE_CLIENT_SECRET", "default_google_client_secret"
    )
    # REDDIT_CLIENT_ID: str = os.getenv("REDDIT_CLIENT_ID", "default_reddit_client_id")
    # REDDIT_CLIENT_SECRET: str = os.getenv("REDDIT_CLIENT_SECRET", "default_reddit_client_secret")

    mail_username: Optional[str] = os.getenv("MAIL_USERNAME")
    mail_password: Optional[str] = os.getenv("MAIL_PASSWORD")
    mail_from: Optional[EmailStr] = os.getenv("MAIL_FROM")
    mail_port: int = int(os.getenv("MAIL_PORT", 587))
    mail_server: Optional[str] = os.getenv("MAIL_SERVER")

    facebook_access_token: Optional[str] = os.getenv("FACEBOOK_ACCESS_TOKEN")
    facebook_app_id: Optional[str] = os.getenv("FACEBOOK_APP_ID")
    facebook_app_secret: Optional[str] = os.getenv("FACEBOOK_APP_SECRET")
    twitter_api_key: Optional[str] = os.getenv("TWITTER_API_KEY")
    twitter_api_secret: Optional[str] = os.getenv("TWITTER_API_SECRET")
    twitter_access_token: Optional[str] = os.getenv("TWITTER_ACCESS_TOKEN")
    twitter_access_token_secret: Optional[str] = os.getenv(
        "TWITTER_ACCESS_TOKEN_SECRET"
    )

    huggingface_api_token: Optional[str] = os.getenv("HUGGINGFACE_API_TOKEN")
    refresh_secret_key: Optional[str] = os.getenv("REFRESH_SECRET_KEY")
    default_language: str = os.getenv("DEFAULT_LANGUAGE", "ar")
    followers_visibility: str = os.getenv("FOLLOWERS_VISIBILITY", "public")
    followers_custom_visibility: dict[str, Any] = {}
    followers_sort_preference: str = os.getenv("FOLLOWERS_SORT_PREFERENCE", "date")
    default_block_type: str = os.getenv("DEFAULT_BLOCK_TYPE", "temporary")
    allow_reposts: Optional[bool] = _env_flag("ALLOW_REPOSTS", default=None)
    ui_settings: Optional[dict[str, Any]] = None
    notifications_settings: Optional[dict[str, Any]] = None

    firebase_api_key: Optional[str] = os.getenv("FIREBASE_API_KEY")
    firebase_auth_domain: Optional[str] = os.getenv("FIREBASE_AUTH_DOMAIN")
    firebase_project_id: Optional[str] = os.getenv("FIREBASE_PROJECT_ID")
    firebase_storage_bucket: Optional[str] = os.getenv("FIREBASE_STORAGE_BUCKET")
    firebase_messaging_sender_id: Optional[str] = os.getenv(
        "FIREBASE_MESSAGING_SENDER_ID"
    )
    firebase_app_id: Optional[str] = os.getenv("FIREBASE_APP_ID")
    firebase_measurement_id: Optional[str] = os.getenv("FIREBASE_MEASUREMENT_ID")

    NOTIFICATION_RETENTION_DAYS: int = 90
    MAX_BULK_NOTIFICATIONS: int = 1000
    NOTIFICATION_QUEUE_TIMEOUT: int = 30
    NOTIFICATION_BATCH_SIZE: int = 100
    DEFAULT_NOTIFICATION_CHANNEL: str = "in_app"

    rsa_private_key_path: str = os.getenv(
        "RSA_PRIVATE_KEY_PATH", str(BASE_DIR / "private_key.pem")
    )
    rsa_public_key_path: str = os.getenv(
        "RSA_PUBLIC_KEY_PATH", str(BASE_DIR / "public_key.pem")
    )

    REDIS_URL: str = os.getenv("REDIS_URL")
    CELERY_BROKER_URL: str = os.getenv("CELERY_BROKER_URL", "redis://localhost:6379/0")
    CELERY_BACKEND_URL: str = os.getenv(
        "CELERY_BACKEND_URL", "redis://localhost:6379/0"
    )
    static_root: str = os.getenv("STATIC_ROOT", str(BASE_DIR / "static"))
    uploads_root: str = os.getenv("UPLOADS_ROOT", str(BASE_DIR / "uploads"))
    static_cache_control: Optional[str] = os.getenv(
        "STATIC_CACHE_CONTROL", "public, max-age=3600"
    )
    uploads_cache_control: Optional[str] = os.getenv(
        "UPLOADS_CACHE_CONTROL", "public, max-age=3600"
    )

    typesense_enabled: bool = bool(_env_flag("TYPESENSE_ENABLED", default=False))
    typesense_host: str = os.getenv("TYPESENSE_HOST", "localhost")
    typesense_port: int = int(os.getenv("TYPESENSE_PORT", 8108))
    typesense_protocol: str = os.getenv("TYPESENSE_PROTOCOL", "http")
    typesense_api_key: str = os.getenv("TYPESENSE_API_KEY", "")
    typesense_collection: str = os.getenv("TYPESENSE_COLLECTION", "posts")

    LINKEDIN_CLIENT_ID: str = os.getenv("LINKEDIN_CLIENT_ID", "")
    LINKEDIN_CLIENT_SECRET: str = os.getenv("LINKEDIN_CLIENT_SECRET", "")
    REDDIT_CLIENT_ID: str = os.getenv("REDDIT_CLIENT_ID", "")
    REDDIT_CLIENT_SECRET: str = os.getenv("REDDIT_CLIENT_SECRET", "")
    REDDIT_USER_AGENT: str = os.getenv("REDDIT_USER_AGENT", "fastapi-app/1.0")

    _rsa_private_key: str = PrivateAttr()
    _rsa_public_key: str = PrivateAttr()

    redis_client: ClassVar[redis.Redis] = None

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        env_override = os.getenv("APP_ENV")
        if env_override:
            object.__setattr__(self, "environment", env_override)
        self._rsa_private_key = self._read_key_file(
            self.rsa_private_key_path, "private"
        )
        self._rsa_public_key = self._read_key_file(self.rsa_public_key_path, "public")

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

        cors_env = os.getenv("CORS_ORIGINS")
        if cors_env:
            origins = [
                origin.strip() for origin in cors_env.split(",") if origin.strip()
            ]
        elif self.cors_origins:
            origins = self.cors_origins
        else:
            origins = [
                "https://example.com",
                "https://www.example.com",
            ]
        object.__setattr__(self, "cors_origins", origins)

        hosts_raw = self.allowed_hosts or os.getenv("ALLOWED_HOSTS", "")
        hosts: list[str]
        if hosts_raw:
            try:
                hosts = [h.strip() for h in json.loads(hosts_raw)]
            except Exception:
                hosts = [h.strip() for h in str(hosts_raw).split(",") if h.strip()]
        else:
            hosts = ["localhost", "127.0.0.1", "testserver"]
        # Only force-add testserver when running tests to keep prod lists intact.
        env_lower = self.environment.lower()
        if env_lower == "test" and "testserver" not in hosts:
            hosts.append("testserver")
        object.__setattr__(self, "allowed_hosts", hosts)

        env_force_https = os.getenv("FORCE_HTTPS")
        if self.environment.lower() == "production":
            if env_force_https is None or env_force_https.strip() == "":
                object.__setattr__(self, "force_https", True)
            else:
                lowered = env_force_https.lower()
                object.__setattr__(
                    self,
                    "force_https",
                    lowered not in {"0", "false", "no", "off"},
                )

    def get_database_url(self, *, use_test: bool = False) -> str:
        """Resolve the SQLAlchemy database URL for runtime or tests.

        Priority: explicit `DATABASE_URL` (or `_test` variant when requested),
        then composed Postgres parts, then `TEST_DATABASE_URL`, finally sqlite fallback.
        Enforces dedicated test DB names to avoid destructive writes to prod data.
        """
        effective_use_test = bool(use_test)

        if effective_use_test:
            test_url = self._resolve_test_database_url()
            if test_url:
                if test_url.startswith("sqlite"):
                    return test_url
                if "_test" not in test_url and "test.db" not in test_url:
                    raise ValueError(
                        "Test database URL must point to a dedicated test database (contains '_test')."
                    )
                return test_url

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

    def _resolve_test_database_url(self) -> Optional[str]:
        """
        Build a test database URL.
        Priority:
        1) Explicit TEST_DATABASE_URL env.
        2) Derive from DATABASE_URL with a *_test suffix (or reuse sqlite).
        3) Derive from Postgres components with a *_test suffix.
        4) Fallback to sqlite for ad-hoc local runs.
        """
        if self.test_database_url:
            return self.test_database_url

        if self.database_url:
            try:
                # Prefer safe derivation using SQLAlchemy URL parsing when available.
                from sqlalchemy.engine import make_url  # type: ignore

                url = make_url(self.database_url)
                if url.drivername.startswith("sqlite"):
                    return str(url)
                db_name = url.database or ""
                suffix_name = (
                    db_name if db_name.endswith("_test") else f"{db_name}_test"
                )
                url = url.set(database=suffix_name)
                return str(url)
            except Exception:
                if "sqlite" in self.database_url:
                    return self.database_url

        if (
            self.database_hostname
            and self.database_username
            and self.database_password
            and self.database_name
        ):
            test_db_name = f"{self.database_name}_test"
            base_url = (
                f"postgresql+psycopg2://{self.database_username}:{self.database_password}"
                f"@{self.database_hostname}:{self.database_port}/{test_db_name}"
            )
            if self.database_ssl_mode:
                return f"{base_url}?sslmode={self.database_ssl_mode}"
            return base_url

        # Final fallback: keep prior sqlite behavior when no Postgres info is present.
        return "sqlite:///./test.db"

    def _read_key_file(self, filename: str, key_type: str) -> str:
        """Resolve and read RSA key files with repo-root fallback; reject missing/empty keys."""
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
    def redis_url(self) -> Optional[str]:
        """
        Backward-compatible accessor used across the codebase.
        Prefer REDIS_URL env but tolerate missing attribute access.
        """
        return getattr(self, "REDIS_URL", None)

    @property
    def mail_config(self) -> ConnectionConfig:
        from_address = self.mail_from or "noreply@example.com"
        config_data = {
            # FastMail requires string fields; fallback to empty strings in test/CI.
            "MAIL_USERNAME": self.mail_username or "",
            "MAIL_PASSWORD": self.mail_password or "",
            "MAIL_FROM": from_address,
            "MAIL_PORT": self.mail_port,
            "MAIL_SERVER": self.mail_server or "",
            "MAIL_FROM_NAME": "Your App Name",
            "MAIL_STARTTLS": True,
            "MAIL_SSL_TLS": False,
            "USE_CREDENTIALS": True,
        }
        return CustomConnectionConfig(**config_data)
