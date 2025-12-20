# ruff: noqa: E402
import os
import asyncio
import atexit
from typing import Any

import psycopg2
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
os.environ["REDIS_URL"] = ""

from app import models
from app.core.config import settings
from app.core.database import Base, get_db
from app.core.cache.redis_cache import cache_manager
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
os.environ["REDIS_URL"] = ""

# Force Redis off during tests to avoid real network calls.
settings.__class__.redis_client = None
object.__setattr__(settings, "redis_client", None)
# Align settings with test environment even if loaded before env vars
object.__setattr__(settings, "environment", "test")

# postgres_test_url = settings.get_database_url(use_test=True)
# os.environ["DATABASE_URL"] = postgres_test_url
# settings.test_database_url = postgres_test_url
# settings.database_url = postgres_test_url
# Prefer explicit test DB settings; otherwise default to local SQLite to avoid
# accidentally connecting to production/staging databases during tests.
test_db_url = (
    os.environ.get("TEST_DATABASE_URL")
    or os.environ.get("LOCAL_TEST_DATABASE_URL")
    or getattr(settings, "test_database_url", None)
    or "sqlite:///./tests/test.db"
)

# Safety: never run tests against a non-test Postgres database.
try:
    parsed_url = make_url(test_db_url)
    if parsed_url.drivername.startswith("postgresql") and parsed_url.database:
        if not parsed_url.database.endswith("_test"):
            raise RuntimeError(
                f"Refusing to run tests against non-test database '{parsed_url.database}'. "
                "Set LOCAL_TEST_DATABASE_URL/TEST_DATABASE_URL to a dedicated *_test database."
            )
except Exception:
    # If parsing fails we'll rely on engine creation to surface a clear error.
    pass

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
    database_url = settings.test_database_url
    url = make_url(database_url)
    engine_kwargs = {"echo": False}

    _ensure_database_exists(url)

    if url.drivername.startswith("sqlite"):
        engine_kwargs["connect_args"] = {"check_same_thread": False}

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
# Drop leftover enum types in Postgres to avoid duplicate creation errors
def _drop_enum_types(engine):
    if engine.dialect.name != "postgresql":
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
try:
    Base.metadata.drop_all(bind=engine)
except Exception:
    pass


def _reset_schema(engine):
    """Force-drop and recreate public schema to avoid duplicate table errors in Postgres."""
    if engine.dialect.name != "postgresql":
        return
    with engine.connect() as conn:
        conn.execute(text("DROP SCHEMA IF EXISTS public CASCADE;"))
        conn.execute(text("CREATE SCHEMA public;"))


_reset_schema(engine)
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base.metadata.create_all(bind=engine)


@pytest.fixture(scope="function")
def session():
    """إنشاء جلسة قاعدة بيانات جديدة لكل اختبار"""
    with engine.begin() as connection:
        if engine.dialect.name == "sqlite":
            for table in reversed(Base.metadata.sorted_tables):
                connection.execute(table.delete())
        else:
            table_names = ", ".join(
                f'"{tbl.name}"' for tbl in Base.metadata.sorted_tables
            )
            if table_names:
                connection.execute(
                    text(f"TRUNCATE {table_names} RESTART IDENTITY CASCADE")
                )
    db = TestingSessionLocal()
    try:
        yield db
    finally:
        db.close()


@pytest.fixture(scope="function")
def db_session(session):
    """اسم مستعار لـ session للتوافق مع الاختبارات التي تستخدم db_session"""
    return session


@pytest.fixture(scope="function")
def client(session):
    def override_get_db():
        try:
            yield session
        finally:
            session.close()

    app.dependency_overrides[get_db] = override_get_db
    with TestClient(app) as test_client:
        try:
            yield test_client
        finally:
            app.dependency_overrides.clear()


@pytest.fixture(autouse=True, scope="function")
def _reset_redis_health():
    """Reset Redis configuration/state between tests to avoid cross-test leakage."""
    object.__setattr__(settings, "REDIS_URL", os.getenv("REDIS_URL", ""))
    cache_manager.redis = None
    cache_manager.enabled = False
    cache_manager.failed_init = False
    yield


@pytest.fixture(scope="function")
def test_user(client):
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
    return create_access_token({"user_id": test_user["id"]})


@pytest.fixture(scope="function")
def test_user_token_headers(token):
    """توفير ترويسة المصادقة مباشرة"""
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture(scope="function")
def authorized_client(client, token):
    client.headers.update({"Authorization": f"Bearer {token}"})
    return client


@pytest.fixture(scope="function")
def test_post(session, test_user):
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
    with engine.begin() as connection:
        if engine.dialect.name == "sqlite":
            for table in reversed(Base.metadata.sorted_tables):
                connection.execute(table.delete())
        else:
            table_names = ", ".join(
                f'"{tbl.name}"' for tbl in Base.metadata.sorted_tables
            )
            if table_names:
                connection.execute(
                    text(f"TRUNCATE {table_names} RESTART IDENTITY CASCADE")
                )
    yield
