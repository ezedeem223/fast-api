"""Test module for conftest."""
# ruff: noqa: E402
import asyncio
import atexit
import importlib
import os
from typing import Any

import psycopg2
import redis
import pytest

from tests.testclient import TestClient


class ClosingEventLoopPolicy(asyncio.DefaultEventLoopPolicy):
    """Event loop policy that force-closes any leftover loops on interpreter exit."""

    def __init__(self):
        super().__init__()
        self._loops = []

    def new_event_loop(self):
        loop = super().new_event_loop()
        self._loops.append(loop)
        return loop

    def close_all(self):
        for loop in list(self._loops):
            if not loop.is_closed():
                loop.close()


# Ensure stray loops don't trigger ResourceWarning at shutdown.
_closing_policy = ClosingEventLoopPolicy()
asyncio.set_event_loop_policy(_closing_policy)
atexit.register(_closing_policy.close_all)
from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url
from sqlalchemy.engine.url import URL
from sqlalchemy.orm import sessionmaker

# Set testing environment flags before importing the app or settings
os.environ.setdefault("APP_ENV", "test")
os.environ["DISABLE_EXTERNAL_NOTIFICATIONS"] = "1"
os.environ["ENABLE_TRANSLATION"] = "0"
os.environ.setdefault("ANYIO_BACKENDS", "asyncio")
_USE_REAL = os.getenv("USE_REAL_SERVICES") == "1" or bool(os.getenv("REMOTE_BASE_URL"))
if not _USE_REAL:
    os.environ["REDIS_URL"] = ""

from app import models
from app.core.cache import redis_cache as rc
from app.core.cache.redis_cache import cache_manager
from app.core.config import settings
from app.core.database import Base, get_db
from app.main import app
from app.oauth2 import create_access_token


class AttrDict(dict):
    """Dict with attribute-style access for fixtures."""

    def __getattr__(self, item: str) -> Any:
        try:
            return self[item]
        except KeyError as exc:
            raise AttributeError(item) from exc


os.environ["APP_ENV"] = "test"
os.environ["DISABLE_EXTERNAL_NOTIFICATIONS"] = "1"
os.environ["ENABLE_TRANSLATION"] = "0"
os.environ.setdefault("ANYIO_BACKENDS", "asyncio")

# Align settings with test environment even if loaded before env vars
object.__setattr__(settings, "environment", "test")


def _use_sqlite_for_tests() -> bool:
    """Return True when tests should prefer SQLite instead of Postgres."""
    return os.getenv("PYTEST_SQLITE", "").lower() in {"1", "true", "yes", "on"}


def _resolve_test_db_url() -> str:
    """Resolve the test DB URL for pytest runs (Postgres by default, optional SQLite)."""
    explicit = os.environ.get("LOCAL_TEST_DATABASE_URL") or os.environ.get(
        "TEST_DATABASE_URL"
    )
    if _use_sqlite_for_tests():
        if explicit and explicit.startswith("sqlite"):
            return explicit
        return "sqlite:///./tests/pytest_sqlite.db"
    if explicit:
        return explicit
    try:
        return settings.get_database_url(use_test=True)
    except Exception as exc:
        raise RuntimeError(
            "Test database is not configured. Set LOCAL_TEST_DATABASE_URL, "
            "TEST_DATABASE_URL, or DATABASE_URL/DATABASE_* for a Postgres *_test database."
        ) from exc


# postgres_test_url = settings.get_database_url(use_test=True)
# os.environ["DATABASE_URL"] = postgres_test_url
# settings.test_database_url = postgres_test_url
# settings.database_url = postgres_test_url
test_db_url = _resolve_test_db_url()
try:
    parsed_url = make_url(test_db_url)
except Exception as exc:
    raise RuntimeError(f"Invalid test database URL: {exc}") from exc

if not parsed_url.drivername.startswith("postgresql"):
    if not _use_sqlite_for_tests():
        raise RuntimeError(
            f"Tests require Postgres, got '{parsed_url.drivername}'. "
            "Set LOCAL_TEST_DATABASE_URL/TEST_DATABASE_URL to a Postgres *_test database."
        )
elif not parsed_url.database or not parsed_url.database.endswith("_test"):
    raise RuntimeError(
        f"Refusing to run tests against non-test database '{parsed_url.database}'. "
        "Set LOCAL_TEST_DATABASE_URL/TEST_DATABASE_URL to a dedicated *_test database."
    )

settings.test_database_url = test_db_url
settings.database_url = test_db_url
os.environ["DATABASE_URL"] = test_db_url
# Disable rate limiting in tests explicitly
from app.core.middleware import rate_limit  # noqa: E402

if hasattr(rate_limit.limiter, "enabled"):
    rate_limit.limiter.enabled = False


# Ensure pytest-asyncio sees a default fixture loop scope so it doesn't emit deprecation warnings.
@pytest.hookimpl(tryfirst=True)
def pytest_configure(config):
    # Ensure pytest knows about the asyncio config key even if plugin versions differ.
    """Helper for pytest configure."""
    if "asyncio_default_fixture_loop_scope" not in config._parser._inidict:
        config._parser.addini(
            "asyncio_default_fixture_loop_scope",
            "Default asyncio fixture loop scope.",
            default="function",
        )
    try:
        has_setting = bool(config.getini("asyncio_default_fixture_loop_scope"))
    except ValueError:
        has_setting = False
    if not has_setting:
        # Inject the default value programmatically to avoid the plugin warning.
        config.inicfg["asyncio_default_fixture_loop_scope"] = "function"
        # Clear ini cache so subsequent getini calls see the injected value.
        config._inicache = {}


def _init_test_engine():
    """Helper for  init test engine."""
    database_url = settings.test_database_url
    url = make_url(database_url)
    engine_kwargs = {"echo": False}

    _ensure_database_exists(url)

    if url.drivername.startswith("sqlite"):
        engine_kwargs["connect_args"] = {"check_same_thread": False}
    else:
        engine_kwargs["connect_args"] = {"connect_timeout": 5}
        engine_kwargs["pool_pre_ping"] = True
        engine_kwargs["pool_recycle"] = 300

    return create_engine(database_url, **engine_kwargs)


def _ensure_database_exists(url: URL) -> None:
    """Create the test database if it doesn't already exist (Postgres only)."""
    if not url.drivername.startswith("postgresql"):
        return

    db_name = url.database
    admin_url = url.set(database="postgres")
    connect_kwargs = {
        "dbname": admin_url.database,
        "user": admin_url.username,
        "password": admin_url.password,
        "host": admin_url.host,
        "port": admin_url.port,
    }
    # Avoid hanging when the Postgres host is unreachable.
    connect_kwargs.setdefault("connect_timeout", 5)
    sslmode = admin_url.query.get("sslmode")
    if sslmode:
        connect_kwargs["sslmode"] = sslmode

    try:
        conn = psycopg2.connect(**connect_kwargs)
        conn.autocommit = True
        with conn.cursor() as cur:
            cur.execute("SELECT 1 FROM pg_database WHERE datname = %s;", (db_name,))
            exists = cur.fetchone()
            if not exists:
                cur.execute(f'CREATE DATABASE "{db_name}";')
        conn.close()
    except Exception:
        # If creation fails (permissions/network), let the later engine creation raise a clear error.
        return

    # Ensure pg_trgm extension exists for indexes used in migrations/models.
    try:
        connect_db_kwargs = connect_kwargs.copy()
        connect_db_kwargs["dbname"] = db_name
        conn = psycopg2.connect(**connect_db_kwargs)
        conn.autocommit = True
        with conn.cursor() as cur:
            cur.execute('CREATE EXTENSION IF NOT EXISTS "pg_trgm";')
        conn.close()
    except Exception:
        return


engine = _init_test_engine()


def _is_remote_db(engine) -> bool:
    """Helper for  is remote db."""
    host = engine.url.host or ""
    return host not in {"localhost", "127.0.0.1"}


# Drop leftover enum types in Postgres to avoid duplicate creation errors
def _drop_enum_types(engine):
    """Helper for  drop enum types."""
    if engine.dialect.name != "postgresql" or _is_remote_db(engine):
        return
    enum_names = [
        "reaction_type",
        "conversation_type_enum",
        "conversation_member_role",
        "message_type",
        "call_type",
        "call_status",
        "screen_share_status",
    ]
    with engine.connect() as conn:
        for name in enum_names:
            try:
                conn.execute(
                    text(
                        f"""
DO $$ BEGIN
    IF EXISTS (SELECT 1 FROM pg_type WHERE typname = '{name}') THEN
        DROP TYPE {name} CASCADE;
    END IF;
END $$;
"""
                    )
                )
                conn.commit()
            except Exception:
                conn.rollback()
                # If the type truly doesn't exist, ignore and continue so tests can proceed.


_drop_enum_types(engine)
# Avoid drop_all failures on Postgres enum dependencies; rely on truncation per-test.
if not _is_remote_db(engine):
    try:
        Base.metadata.drop_all(bind=engine)
    except Exception:
        pass


def _reset_schema(engine):
    """Force-drop and recreate public schema to avoid duplicate table errors in Postgres."""
    if engine.dialect.name != "postgresql" or _is_remote_db(engine):
        return
    with engine.connect() as conn:
        conn.execute(text("DROP SCHEMA IF EXISTS public CASCADE;"))
        conn.execute(text("CREATE SCHEMA public;"))


def _ensure_post_soft_delete_columns(engine) -> None:
    """Ensure posts soft-delete columns exist when using a persistent Postgres test DB."""
    if engine.dialect.name != "postgresql":
        return
    with engine.begin() as conn:
        conn.execute(
            text(
                "ALTER TABLE posts "
                "ADD COLUMN IF NOT EXISTS is_deleted BOOLEAN DEFAULT FALSE"
            )
        )
        conn.execute(
            text(
                "ALTER TABLE posts "
                "ADD COLUMN IF NOT EXISTS deleted_at TIMESTAMPTZ"
            )
        )


_reset_schema(engine)
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base.metadata.create_all(bind=engine)
_ensure_post_soft_delete_columns(engine)


def _terminate_other_connections(connection) -> None:
    """Helper for  terminate other connections."""
    if os.getenv("TEST_DB_TERMINATE_CONNECTIONS") != "1":
        return
    try:
        connection.execute(
            text(
                "SELECT pg_terminate_backend(pid) "
                "FROM pg_stat_activity "
                "WHERE datname = current_database() AND pid <> pg_backend_pid()"
            )
        )
        connection.commit()
    except Exception:
        connection.rollback()


def _verify_external_dependencies() -> None:
    """Print connectivity confirmations for RSA, Postgres, and Redis before tests run."""
    if getattr(settings, "rsa_private_key", None) and getattr(
        settings, "rsa_public_key", None
    ):
        print(
            f"[preflight] RSA keys loaded from {settings.rsa_private_key_path} / {settings.rsa_public_key_path}"
        )
    else:
        raise RuntimeError("RSA keys are not loaded")

    try:
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        print(f"[preflight] Connected to Postgres: {engine.url}")
    except Exception as exc:  # pragma: no cover - fail fast if DB unreachable
        raise RuntimeError(f"Failed to connect to Postgres: {exc}") from exc

    redis_url = os.getenv("REDIS_URL") or getattr(settings, "redis_url", None)
    if not redis_url:
        raise RuntimeError("REDIS_URL not set for connectivity check")
    try:
        client = redis.Redis.from_url(
            redis_url, socket_connect_timeout=5, socket_timeout=5, decode_responses=True
        )
        client.ping()
        print(f"[preflight] Connected to Redis: {redis_url}")
    except Exception as exc:  # pragma: no cover - fail fast on connectivity
        raise RuntimeError(f"Failed to connect to Redis: {exc}") from exc


@pytest.fixture(scope="session", autouse=True)
def verify_external_connections():
    """Ensure external dependencies are reachable before running tests."""
    use_real = os.getenv("USE_REAL_SERVICES") == "1"
    remote_base = os.getenv("REMOTE_BASE_URL")

    if remote_base:
        _verify_remote_readyz()
        return

    if use_real:
        _verify_external_dependencies()
    else:
        # Default path: disable Redis to avoid hitting internal Render hosts in local/CI.
        os.environ["REDIS_URL"] = ""
        try:
            settings.__class__.redis_client = None
            object.__setattr__(settings, "redis_client", None)
            object.__setattr__(settings, "REDIS_URL", "")
        except Exception:
            pass
        cache_manager.redis = None
        cache_manager.enabled = False
        cache_manager.failed_init = False
        print("[preflight] skipped (USE_REAL_SERVICES not set and REMOTE_BASE_URL not provided)")


@pytest.fixture(scope="function")
def session(_seed_base_users):
    """Database session fixture scoped to a single test."""
    db = TestingSessionLocal()
    try:
        yield db
    finally:
        db.close()


@pytest.fixture(scope="function")
def db_session(session):
    """Alias for session to keep legacy tests using db_session working."""
    return session


@pytest.fixture(scope="function")
def client(session):
    """Pytest fixture for client."""
    def override_get_db():
        yield session

    app.dependency_overrides[get_db] = override_get_db
    with TestClient(app) as test_client:
        try:
            yield test_client
        finally:
            app.dependency_overrides.clear()


@pytest.fixture(autouse=True, scope="function")
def _reset_redis_health():
    """Reset Redis configuration/state between tests to avoid leakage; tests can override as needed."""
    # Restore real redis factory
    rc.redis = importlib.import_module("redis.asyncio")
    object.__setattr__(settings, "REDIS_URL", os.getenv("REDIS_URL", ""))
    cache_manager.redis = None
    cache_manager.enabled = False
    cache_manager.failed_init = False
    yield


@pytest.fixture(scope="function")
def test_user(client):
    """Pytest fixture for test_user."""
    user_data = {"email": "hello123@gmail.com", "password": "password123"}
    res = client.post("/users/", json=user_data)
    assert res.status_code == 201
    new_user = res.json()
    with TestingSessionLocal() as db:
        db.query(models.User).filter(models.User.id == new_user["id"]).update(
            {"is_verified": True}
        )
        db.commit()
    new_user["password"] = user_data["password"]
    return AttrDict(new_user)


@pytest.fixture(scope="function")
def test_user2(client):
    """Pytest fixture for test_user2."""
    user_data = {"email": "hello3@gmail.com", "password": "password123"}
    res = client.post("/users/", json=user_data)
    assert res.status_code == 201
    new_user = res.json()
    with TestingSessionLocal() as db:
        db.query(models.User).filter(models.User.id == new_user["id"]).update(
            {"is_verified": True}
        )
        db.commit()
    new_user["password"] = user_data["password"]
    return AttrDict(new_user)


@pytest.fixture(scope="function")
def token(test_user):
    """Pytest fixture for token."""
    return create_access_token({"user_id": test_user["id"]})


@pytest.fixture(scope="function")
def test_user_token_headers(token):
    """Provide authorization headers for the test user."""
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture(scope="function")
def authorized_client(client, token):
    """Pytest fixture for authorized_client."""
    client.headers.update({"Authorization": f"Bearer {token}"})
    return client


@pytest.fixture(scope="function")
def test_post(session, test_user):
    """Pytest fixture for test_post."""
    post = models.Post(
        title="Fixture Post",
        content="Fixture post content",
        owner_id=test_user["id"],
    )
    session.add(post)
    session.commit()
    session.refresh(post)
    return {"id": post.id, "title": post.title, "content": post.content}


@pytest.fixture(scope="function")
def test_comment(session, test_post, test_user):
    """Pytest fixture for test_comment."""
    comment = models.Comment(
        content="Fixture comment content",
        owner_id=test_user["id"],
        post_id=test_post["id"],
    )
    session.add(comment)
    session.commit()
    session.refresh(comment)
    return {"id": comment.id, "content": comment.content, "post_id": comment.post_id}


@pytest.fixture(scope="function")
def test_posts(test_user, session, test_user2):
    """Pytest fixture for test_posts."""
    posts_data = [
        {
            "title": "first title",
            "content": "first content",
            "owner_id": test_user["id"],
        },
        {"title": "2nd title", "content": "2nd content", "owner_id": test_user["id"]},
        {"title": "3rd title", "content": "3rd content", "owner_id": test_user["id"]},
        {"title": "3rd title", "content": "3rd content", "owner_id": test_user2["id"]},
    ]
    posts = [models.Post(**post) for post in posts_data]
    session.add_all(posts)
    session.commit()
    return session.query(models.Post).all()


# Autouse cleanup to keep DB isolated across all tests, including those that
# do not explicitly request the session fixture.
@pytest.fixture(autouse=True, scope="function")
def _clean_db_between_tests():
    """Pytest fixture for _clean_db_between_tests."""
    with engine.connect() as connection:
        if engine.dialect.name == "sqlite":
            # SQLite path: delete per table inside a transaction for isolation.
            trans = connection.begin()
            try:
                for table in reversed(Base.metadata.sorted_tables):
                    connection.execute(table.delete())
                trans.commit()
            except Exception:
                trans.rollback()
                raise
            yield
            return

        _terminate_other_connections(connection)
        strategy = _db_clean_strategy()

        def _set_timeouts():
            connection.execute(text("SET LOCAL lock_timeout = '5s'"))
            connection.execute(text("SET LOCAL statement_timeout = '30s'"))

        if strategy == "truncate":
            # Prefer TRUNCATE for speed, fall back to per-table deletes if needed.
            trans = connection.begin()
            try:
                _set_timeouts()
                table_names = ", ".join(
                    f'"{tbl.name}"' for tbl in Base.metadata.sorted_tables
                )
                if table_names:
                    connection.execute(
                        text(f"TRUNCATE {table_names} RESTART IDENTITY CASCADE")
                    )
                trans.commit()
            except Exception:
                trans.rollback()
                trans = connection.begin()
                try:
                    _set_timeouts()
                    for table in reversed(Base.metadata.sorted_tables):
                        connection.execute(table.delete())
                    trans.commit()
                except Exception:
                    trans.rollback()
                    raise
        else:
            trans = connection.begin()
            try:
                _set_timeouts()
                for table in reversed(Base.metadata.sorted_tables):
                    connection.execute(table.delete())
                trans.commit()
            except Exception:
                trans.rollback()
                raise
    yield


def _db_clean_strategy() -> str:
    """Helper for  db clean strategy."""
    override = os.getenv("TEST_DB_CLEAN_STRATEGY", "").lower()
    if override in {"truncate", "delete"}:
        return override
    host = engine.url.host or ""
    if host and host not in {"localhost", "127.0.0.1"}:
        return "delete"
    return "truncate"


@pytest.fixture(autouse=True, scope="function")
def _seed_base_users(_clean_db_between_tests):
    """Pytest fixture for _seed_base_users."""
    seed_count = int(os.getenv("TEST_SEED_USER_COUNT", "20"))
    if seed_count <= 0:
        yield
        return
    with TestingSessionLocal() as db:
        users = [
            models.User(
                id=idx,
                email=f"seed{idx}@example.com",
                hashed_password="x",
                is_verified=True,
            )
            for idx in range(1, seed_count + 1)
        ]
        db.add_all(users)
        db.commit()
        try:
            db.execute(
                text(
                    "SELECT setval(pg_get_serial_sequence('users','id'), "
                    "(SELECT MAX(id) FROM users))"
                )
            )
            db.commit()
        except Exception:
            db.rollback()
    yield
