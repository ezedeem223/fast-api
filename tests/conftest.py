import os

_DEFAULT_ENV_VARS = {
    "DATABASE_HOSTNAME": "localhost",
    "DATABASE_PORT": "5432",
    "DATABASE_PASSWORD": "test-password",
    "DATABASE_NAME": "app",
    "DATABASE_USERNAME": "app",
    "SECRET_KEY": "test-secret-key",
    "REFRESH_SECRET_KEY": "test-refresh-secret-key",
    "ALGORITHM": "HS256",
    "MAIL_USERNAME": "noreply@example.com",
    "MAIL_PASSWORD": "mail-password",
    "MAIL_FROM": "noreply@example.com",
    "MAIL_SERVER": "smtp.example.com",
    "FACEBOOK_ACCESS_TOKEN": "fb-access",
    "FACEBOOK_APP_ID": "fb-app-id",
    "FACEBOOK_APP_SECRET": "fb-app-secret",
    "TWITTER_API_KEY": "tw-api-key",
    "TWITTER_API_SECRET": "tw-api-secret",
    "TWITTER_ACCESS_TOKEN": "tw-access-token",
    "TWITTER_ACCESS_TOKEN_SECRET": "tw-access-secret",
    "HUGGINGFACE_API_TOKEN": "hf-token",
    "FIREBASE_API_KEY": "firebase-api-key",
    "FIREBASE_AUTH_DOMAIN": "firebase-auth-domain",
    "FIREBASE_PROJECT_ID": "firebase-project",
    "FIREBASE_STORAGE_BUCKET": "firebase-bucket",
    "FIREBASE_MESSAGING_SENDER_ID": "firebase-sender",
    "FIREBASE_APP_ID": "firebase-app-id",
    "FIREBASE_MEASUREMENT_ID": "firebase-measurement",
    "RSA_PRIVATE_KEY_PATH": os.path.abspath("private_key.pem"),
    "RSA_PUBLIC_KEY_PATH": os.path.abspath("public_key.pem"),
    "REDIS_URL": "redis://localhost:6379/0",
}

for env_key, env_value in _DEFAULT_ENV_VARS.items():
    os.environ.setdefault(env_key, env_value)

from fastapi.testclient import TestClient
import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker
from sqlalchemy.ext.compiler import compiles
from sqlalchemy.sql.functions import now
from sqlalchemy.sql.schema import DefaultClause
from app.main import app
from app.config import settings
from app.database import get_db, Base
from app.oauth2 import create_access_token
from app import models


@compiles(now, "sqlite")
def _compile_now_sqlite(element, compiler, **kwargs):
    """Ensure NOW() compiles to SQLite-compatible CURRENT_TIMESTAMP."""

    return "CURRENT_TIMESTAMP"

# إعداد URL قاعدة بيانات الاختبار من المتغيرات البيئية أو استخدام قيمة افتراضية
SQLALCHEMY_DATABASE_URL = os.getenv(
    "TEST_DATABASE_URL",
    "sqlite:///./test_app.db",
)

engine_kwargs = {"echo": False}
if SQLALCHEMY_DATABASE_URL.startswith("sqlite"):
    engine_kwargs["connect_args"] = {"check_same_thread": False}

# إنشاء محرك الاتصال بقاعدة بيانات الاختبار
engine = create_engine(SQLALCHEMY_DATABASE_URL, **engine_kwargs)

# تكوين الجلسة المحلية للاختبار
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

# تكييف القيم الافتراضية مع SQLite قبل إنشاء الجداول
if engine.dialect.name == "sqlite":
    from sqlalchemy.sql.elements import TextClause

    for table in Base.metadata.tables.values():
        for column in table.columns:
            default = getattr(column, "server_default", None)
            if default is not None:
                arg = getattr(default, "arg", None)
                if isinstance(arg, TextClause) and arg.text.lower() == "now()":
                    column.server_default = DefaultClause(text("CURRENT_TIMESTAMP"))
            onupdate = getattr(column, "server_onupdate", None)
            if onupdate is not None:
                arg = getattr(onupdate, "arg", None)
                if isinstance(arg, TextClause) and arg.text.lower() == "now()":
                    column.server_onupdate = DefaultClause(text("CURRENT_TIMESTAMP"))

# إنشاء جميع الجداول مرة واحدة عند بدء تشغيل الاختبارات
Base.metadata.create_all(bind=engine)


# Fixture لإنشاء جلسة اختبار جديدة لكل اختبار
@pytest.fixture(scope="function")
def session():
    # قبل كل اختبار: تفريغ بيانات الجداول باستخدام TRUNCATE لتفادي إعادة إنشاء الهيكل
    with engine.begin() as connection:
        if engine.dialect.name == "sqlite":
            for table in reversed(Base.metadata.sorted_tables):
                connection.execute(table.delete())
        else:
            table_names = ", ".join([tbl.name for tbl in Base.metadata.sorted_tables])
            if table_names:
                connection.execute(
                    text(f"TRUNCATE {table_names} RESTART IDENTITY CASCADE")
                )
    db = TestingSessionLocal()
    try:
        yield db
    finally:
        db.close()


# Fixture لإنشاء عميل اختبار يعمل مع جلسة الاختبار
@pytest.fixture(scope="function")
def client(session):
    def override_get_db():
        try:
            yield session
        finally:
            session.close()

    app.dependency_overrides[get_db] = override_get_db
    yield TestClient(app)
    app.dependency_overrides.clear()


# Fixture لإنشاء مستخدم اختبار
@pytest.fixture(scope="function")
def test_user(client):
    user_data = {"email": "hello123@gmail.com", "password": "password123"}
    res = client.post("/users/", json=user_data)
    assert res.status_code == 201
    new_user = res.json()
    new_user["password"] = user_data["password"]
    return new_user


# Fixture لإنشاء مستخدم اختبار آخر
@pytest.fixture(scope="function")
def test_user2(client):
    user_data = {"email": "hello3@gmail.com", "password": "password123"}
    res = client.post("/users/", json=user_data)
    assert res.status_code == 201
    new_user = res.json()
    new_user["password"] = user_data["password"]
    return new_user


# Fixture لإنشاء رمز وصول (access token)
@pytest.fixture(scope="function")
def token(test_user):
    return create_access_token({"user_id": test_user["id"]})


# Fixture لإنشاء عميل مفوض (يحتوي على رأس Authorization)
@pytest.fixture(scope="function")
def authorized_client(client, token):
    client.headers.update({"Authorization": f"Bearer {token}"})
    return client


# Fixture لإضافة مشاركات اختبار إلى قاعدة البيانات
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
