import os

# Force the script to use the lightweight SQLite test database so it can run
# without a provisioned PostgreSQL instance (as done in pytest fixtures).
os.environ["APP_ENV"] = "test"
os.environ["DISABLE_EXTERNAL_NOTIFICATIONS"] = "1"

from app.core.config import settings

test_db_url = settings.test_database_url
os.environ["DATABASE_URL"] = test_db_url
os.environ["REDIS_URL"] = ""
object.__setattr__(settings, "environment", "test")
settings.database_url = test_db_url
settings.__class__.redis_client = None
object.__setattr__(settings, "redis_client", None)

from fastapi.testclient import TestClient
from sqlalchemy.orm import sessionmaker

from app.core.database import Base, build_engine, get_db
from app.routers import search as search_router
from app import models
from app.main import app

test_engine = build_engine(test_db_url)
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=test_engine)
Base.metadata.drop_all(bind=test_engine)
Base.metadata.create_all(bind=test_engine)


def _override_get_db():
    db = TestingSessionLocal()
    try:
        yield db
    finally:
        db.close()


app.dependency_overrides[get_db] = _override_get_db

class FakeClient:
    def __init__(self, post_id):
        self.post_id = post_id
    def search_posts(self, query, limit=10):
        return [{"document": {"post_id": self.post_id}}]

with TestingSessionLocal() as db:
    existing = (
        db.query(models.User)
        .filter(models.User.email == "dummy@example.com")
        .first()
    )
    if not existing:
        user = models.User(email="dummy@example.com", hashed_password="pass")
        db.add(user)
        db.commit()
        db.refresh(user)
    else:
        user = existing

    post = models.Post(title="Hello typesense", content="Body", owner_id=user.id)
    db.add(post)
    db.commit()
    db.refresh(post)

    post_id = post.id

search_router.get_typesense_client = lambda: FakeClient(post_id)

search_router.get_typesense_client = lambda: FakeClient(post.id)
client = TestClient(app)
login = client.post("/users/", json={"email": "temp@example.com", "password": "secret"})
print("create user status", login.status_code)
resp = client.post("/login", data={"username": "temp@example.com", "password": "secret"})
print("login status", resp.status_code)
token = resp.json()["access_token"]
headers = {"Authorization": f"Bearer {token}"}
response = client.post("/search/", json={"query": "Hello", "sort_by": "relevance"}, headers=headers)
print(response.status_code)
print(response.json())
