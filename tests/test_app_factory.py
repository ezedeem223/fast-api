from app.core import app_factory
from tests.testclient import TestClient


def test_create_app_registers_routes(monkeypatch):
    # Stub heavy startup hooks to keep test fast and isolated.
    monkeypatch.setattr(app_factory, "train_content_classifier", lambda: None)
    monkeypatch.setattr(app_factory, "register_startup_tasks", lambda app: None)

    app = app_factory.create_app()
    with TestClient(app) as client:
        resp = client.get("/languages")
        assert resp.status_code == 200
        assert isinstance(resp.json(), dict)

        resp = client.get("/protected-resource")
        assert resp.status_code == 401  # auth required, route exists
