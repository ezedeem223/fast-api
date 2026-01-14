"""
Basic Locust load test hitting health and a sample API route.

Usage:
    LOCUST_HOST=https://fast-api.example.com locust -f scripts/locustfile.py
Environment:
    LOCUST_HOST / HOST: target host (defaults to APP_URL or http://localhost:8000)
"""

import os
from locust import HttpUser, task, between


def _resolve_host() -> str:
    """Helper for  resolve host."""
    return (
        os.getenv("LOCUST_HOST")
        or os.getenv("HOST")
        or os.getenv("APP_URL")
        or "http://localhost:8000"
    )


class FastApiUser(HttpUser):
    """Class FastApiUser."""
    wait_time = between(1, 3)
    host = _resolve_host()

    @task(2)
    def health(self):
        self.client.get("/livez", name="livez")

    @task(1)
    def posts(self):
        self.client.get("/posts?limit=10", name="list_posts")


class AnonymousUser(HttpUser):
    """Class AnonymousUser."""
    wait_time = between(2, 5)
    host = _resolve_host()

    @task
    def homepage(self):
        self.client.get("/", name="home")
