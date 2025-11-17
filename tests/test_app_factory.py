from fastapi.testclient import TestClient

from app.core import app_factory


def test_create_app_registers_routes(monkeypatch):
    monkeypatch.setattr(app_factory, "train_content_classifier", lambda: None)
    monkeypatch.setattr(app_factory, "register_startup_tasks", lambda app: None)

    app = app_factory.create_app()
    client = TestClient(app)

    resp = client.get("/languages")
    assert resp.status_code == 200
    assert isinstance(resp.json(), dict)

    resp = client.get("/protected-resource")
    assert resp.status_code == 401  # auth required, route exists
