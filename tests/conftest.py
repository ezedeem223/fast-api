import os

os.environ["TESTING"] = "1"
os.environ.setdefault("DATABASE_URL", "sqlite:///./test_app.db")

import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from app.main import create_application


@pytest.fixture(scope="session")
def app():
    return create_application()


@pytest.fixture(scope="session")
def client(app):
    with TestClient(app) as test_client:
        yield test_client
