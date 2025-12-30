"""API router aggregation utilities.

Exposes `api_router` so app_factory can include all HTTP routes from one place.
"""

from .router import api_router

__all__ = ["api_router"]
