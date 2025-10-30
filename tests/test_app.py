from fastapi.testclient import TestClient

from app.main import create_application


def test_root_endpoint(client: TestClient):
    response = client.get("/")
    assert response.status_code == 200
    assert response.json()["message"].startswith("Welcome")


def test_languages_endpoint(client: TestClient):
    response = client.get("/languages")
    assert response.status_code == 200
    data = response.json()
    assert "en" in data
    assert "ar" in data


def test_translate_endpoint_defaults(client: TestClient):
    response = client.post("/translate", json={"text": "مرحبا", "source_lang": "ar", "target_lang": "en"})
    assert response.status_code == 200
    payload = response.json()
    assert payload["source_lang"] == "ar"
    assert payload["target_lang"] == "en"
    assert "translated" in payload


def test_content_language_header_respects_accept_language(client: TestClient):
    response = client.get("/", headers={"Accept-Language": "fr"})
    assert response.headers["Content-Language"] == "fr"


def test_banned_ip_returns_forbidden(monkeypatch):
    import app.main as main_module

    monkeypatch.setattr(main_module, "is_ip_banned", lambda db, ip: True)
    test_app = create_application()
    with TestClient(test_app) as local_client:
        response = local_client.get("/")
    assert response.status_code == 403
