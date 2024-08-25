# tests/test_edge_cases.py

import pytest
from app import schemas


def test_create_post_with_empty_title(authorized_client):
    res = authorized_client.post(
        "/posts/", json={"title": "", "content": "Test content"}
    )
    assert res.status_code == 422  # Unprocessable Entity
    assert "value_error.missing" in res.json()["detail"][0]["type"]


def test_create_post_with_long_title(authorized_client):
    long_title = "a" * 300  # عنوان طويل جدًا يتجاوز الطول المقبول
    res = authorized_client.post(
        "/posts/", json={"title": long_title, "content": "Test content"}
    )
    assert res.status_code == 422  # Unprocessable Entity
    assert "value_error.any_str.max_length" in res.json()["detail"][0]["type"]


def test_create_post_with_empty_content(authorized_client):
    res = authorized_client.post("/posts/", json={"title": "Test title", "content": ""})
    assert res.status_code == 422  # Unprocessable Entity
    assert "value_error.missing" in res.json()["detail"][0]["type"]


def test_vote_on_nonexistent_post(authorized_client):
    res = authorized_client.post("/vote/", json={"post_id": 9999, "dir": 1})
    assert res.status_code == 404  # Not Found


def test_delete_nonexistent_post(authorized_client):
    res = authorized_client.delete("/posts/9999")
    assert res.status_code == 404  # Not Found


def test_unauthorized_user_access_protected_route(client):
    res = client.get("/posts/")
    assert res.status_code == 401  # Unauthorized


def test_create_post_unauthorized(client):
    res = client.post(
        "/posts/", json={"title": "Test title", "content": "Test content"}
    )
    assert res.status_code == 401  # Unauthorized
