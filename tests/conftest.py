from fastapi.testclient import TestClient
import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker
from app.main import app
from app.config import settings
from app.database import get_db, Base
from app.oauth2 import create_access_token
from app import models
import os

# إعداد URL قاعدة بيانات الاختبار من المتغيرات البيئية أو استخدام قيمة افتراضية
SQLALCHEMY_DATABASE_URL = (
    f"postgresql://{settings.database_username}:"
    f"{settings.database_password}@"
    f"{settings.database_hostname}:"
    f"{settings.database_port}/"
    f"{settings.database_name}_test"
)

# إنشاء محرك الاتصال بقاعدة بيانات الاختبار
engine = create_engine(SQLALCHEMY_DATABASE_URL, echo=False)

# تكوين الجلسة المحلية للاختبار
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

# إنشاء جميع الجداول مرة واحدة عند بدء تشغيل الاختبارات
Base.metadata.create_all(bind=engine)


# Fixture لإنشاء جلسة اختبار جديدة لكل اختبار
@pytest.fixture(scope="function")
def session():
    # قبل كل اختبار: تفريغ بيانات الجداول باستخدام TRUNCATE لتفادي إعادة إنشاء الهيكل
    with engine.connect() as connection:
        table_names = ", ".join([tbl.name for tbl in Base.metadata.sorted_tables])
        connection.execute(text(f"TRUNCATE {table_names} RESTART IDENTITY CASCADE"))
        connection.commit()
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
