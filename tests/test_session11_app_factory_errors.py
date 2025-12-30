from slowapi.errors import RateLimitExceeded
from sqlalchemy.exc import SQLAlchemyError

from app.core import error_handlers, exceptions
from fastapi import Body, FastAPI
from fastapi.testclient import TestClient


def _make_app():
    app = FastAPI()
    app.state.environment = "test"
    error_handlers.register_exception_handlers(app)
    return app


def test_app_exception_handler_returns_standard_json():
    app = _make_app()

    @app.get("/boom")
    async def boom():
        raise exceptions.AppException(
            status_code=418,
            error_code="teapot",
            message="short and stout",
            details={"hint": "tilt"},
        )

    with TestClient(app) as client:
        resp = client.get("/boom")
        body = resp.json()
        assert resp.status_code == 418
        assert body["error"]["code"] == "teapot"
        assert body["error"]["details"]["hint"] == "tilt"
        assert body["path"] == "/boom"


def test_validation_and_rate_limit_handlers():
    app = _make_app()

    @app.post("/validate")
    async def validate(name: str = Body(..., embed=True)):
        return {"ok": True}

    @app.get("/ratelimit")
    async def ratelimit():
        class DummyLimit:
            error_message = "hit limit"
            reset_in = 1

        raise RateLimitExceeded(DummyLimit())

    with TestClient(app, raise_server_exceptions=False) as client:
        bad = client.post("/validate", json={})
        body = bad.json()
        assert bad.status_code == 422
        assert body["error"]["code"] == "validation_error"

        rl = client.get("/ratelimit")
        rl_body = rl.json()
        assert rl.status_code == 429
        assert rl_body["error"]["code"] == "rate_limit_exceeded"


def test_sqlalchemy_and_generic_error_handler(monkeypatch):
    app = _make_app()

    @app.get("/dberr")
    async def dberr():
        raise SQLAlchemyError("db is down")

    @app.get("/general")
    async def general():
        raise RuntimeError("explode")

    with TestClient(app, raise_server_exceptions=False) as client:
        db_resp = client.get("/dberr")
        assert db_resp.status_code == 500
        assert db_resp.json()["error"]["code"] == "database_error"

        gen = client.get("/general")
        gen_body = gen.json()
        assert gen.status_code == 500
        assert gen_body["error"]["code"] == "internal_server_error"
        # in test env we should see raw message in details
        assert "explode" in gen_body["error"]["message"]
        assert "RuntimeError" in "\n".join(
            gen_body["error"]["details"].get("traceback", [])
        )
