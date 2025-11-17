import os
os.environ.setdefault('APP_ENV','test')
os.environ.setdefault('DISABLE_EXTERNAL_NOTIFICATIONS','1')

from fastapi.testclient import TestClient
from tests.conftest import TestingSessionLocal, engine
from app.core.database import Base, get_db
from app.main import app
from app import models

with engine.begin() as connection:
    for table in reversed(Base.metadata.sorted_tables):
        connection.execute(table.delete())

session = TestingSessionLocal()

def override_get_db():
    try:
        yield session
    finally:
        pass

app.dependency_overrides[get_db] = override_get_db
client = TestClient(app)

user1 = client.post('/users/', json={'email': 'u1@example.com', 'password': 'pass'}).json()
client.post('/users/', json={'email': 'u2@example.com', 'password': 'pass'})
login = client.post('/login', data={'username': 'u1@example.com', 'password': 'pass'})
client.headers.update({'Authorization': f"Bearer {login.json()['access_token']}"})

post = models.Post(title='Title', content='Body', owner_id=user1['id'])
session.add(post)
session.commit()
session.refresh(post)

resp = client.post('/report/', json={'post_id': post.id, 'reason': 'spam'})
print('status', resp.status_code)
print('detail', resp.json())
