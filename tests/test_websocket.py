import pytest
from fastapi.testclient import TestClient


def test_websocket_echo(client: TestClient):
    with client.websocket_connect("/ws/42") as websocket:
        websocket.send_text("hello")
        data = websocket.receive_json()
        assert data["message"] == "hello"
        assert data["type"] == "simple_notification"
