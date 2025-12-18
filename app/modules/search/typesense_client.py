"""Minimal Typesense client wrapper for search offload; cached when enabled."""

from __future__ import annotations

from typing import List, Optional

import requests

from app.core.config import settings


class TypesenseClient:
    def __init__(self, *, host: str, port: str, protocol: str, api_key: str, collection: str):
        self.base_url = f"{protocol}://{host}:{port}"
        self.collection = collection
        self.headers = {"X-TYPESENSE-API-KEY": api_key}

    def search_posts(self, query: str, limit: int = 10) -> List[dict]:
        payload = {
            "q": query,
            "query_by": "content,title",
            "per_page": limit,
        }
        response = requests.post(
            f"{self.base_url}/collections/{self.collection}/documents/search",
            json=payload,
            headers=self.headers,
            timeout=3,
        )
        response.raise_for_status()
        data = response.json()
        return data.get("hits", [])


_cached_client: Optional[TypesenseClient] = None


def get_typesense_client() -> Optional[TypesenseClient]:
    global _cached_client
    if not settings.typesense_enabled:
        return None
    if _cached_client is None:
        _cached_client = TypesenseClient(
            host=settings.typesense_host,
            port=settings.typesense_port,
            protocol=settings.typesense_protocol,
            api_key=settings.typesense_api_key,
            collection=settings.typesense_collection,
        )
    return _cached_client
