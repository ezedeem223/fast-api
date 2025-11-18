from fastapi.testclient import TestClient
from app.main import app
from app.routers import search as search_router
from app import models
from app.core.database import SessionLocal

class FakeClient:
    def __init__(self, post_id):
        self.post_id = post_id
    def search_posts(self, query, limit=10):
        return [{"document": {"post_id": self.post_id}}]

db = SessionLocal()
existing = db.query(models.User).filter(models.User.email == "dummy@example.com").first()
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
