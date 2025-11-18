import os
os.environ["APP_ENV"] = "test"
os.environ["DISABLE_EXTERNAL_NOTIFICATIONS"] = "1"
os.environ["ENABLE_TRANSLATION"] = "0"
os.environ["REDIS_URL"] = ""

from fastapi.testclient import TestClient
import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url
from sqlalchemy.orm import sessionmaker

from app.core.config import settings

# Force Redis off during tests to avoid real network calls.
settings.__class__.redis_client = None
object.__setattr__(settings, "redis_client", None)

settings.database_url = settings.test_database_url
os.environ["DATABASE_URL"] = settings.test_database_url

from app import models
from app.core.database import Base, get_db
from app.main import app
from app.oauth2 import create_access_token


def _init_test_engine():
    database_url = settings.get_database_url(use_test=True)
    url = make_url(database_url)
    engine_kwargs = {"echo": False}

    if url.drivername.startswith("sqlite"):
        engine_kwargs["connect_args"] = {"check_same_thread": False}

    return create_engine(database_url, **engine_kwargs)


engine = _init_test_engine()
Base.metadata.drop_all(bind=engine)
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base.metadata.create_all(bind=engine)


@pytest.fixture(scope="function")
def session():
    with engine.begin() as connection:
        if engine.dialect.name == "sqlite":
            for table in reversed(Base.metadata.sorted_tables):
                connection.execute(table.delete())
        else:
            table_names = ", ".join(f'"{tbl.name}"' for tbl in Base.metadata.sorted_tables)
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
def client(session):
    def override_get_db():
        try:
            yield session
        finally:
            session.close()

    app.dependency_overrides[get_db] = override_get_db
    yield TestClient(app)
    app.dependency_overrides.clear()


@pytest.fixture(scope="function")
def test_user(client):
    user_data = {"email": "hello123@gmail.com", "password": "password123"}
    res = client.post("/users/", json=user_data)
    assert res.status_code == 201
    new_user = res.json()
    with TestingSessionLocal() as db:
        db.query(models.User).filter(models.User.id == new_user["id"]).update({"is_verified": True})
        db.commit()
    new_user["password"] = user_data["password"]
    return new_user


@pytest.fixture(scope="function")
def test_user2(client):
    user_data = {"email": "hello3@gmail.com", "password": "password123"}
    res = client.post("/users/", json=user_data)
    assert res.status_code == 201
    new_user = res.json()
    with TestingSessionLocal() as db:
        db.query(models.User).filter(models.User.id == new_user["id"]).update({"is_verified": True})
        db.commit()
    new_user["password"] = user_data["password"]
    return new_user


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
def token(test_user):
    return create_access_token({"user_id": test_user["id"]})


@pytest.fixture(scope="function")
def authorized_client(client, token):
    client.headers.update({"Authorization": f"Bearer {token}"})
    return client


@pytest.fixture(scope="function")
def test_posts(test_user, session, test_user2):
    posts_data = [
        {"title": "first title", "content": "first content", "owner_id": test_user["id"]},
        {"title": "2nd title", "content": "2nd content", "owner_id": test_user["id"]},
        {"title": "3rd title", "content": "3rd content", "owner_id": test_user["id"]},
        {"title": "3rd title", "content": "3rd content", "owner_id": test_user2["id"]},
    ]
    posts = [models.Post(**post) for post in posts_data]
    session.add_all(posts)
    session.commit()
    return session.query(models.Post).all()
