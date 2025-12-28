"""Lightweight models package initialiser.

- Exposes the shared SQLAlchemy `Base`.
- Lazily exposes all domain models via module-level attribute access so importing
  `app.core.database` (which pulls `Base`) doesn't eagerly import every model.
- Keeps Alembic metadata discovery cheap by deferring heavy imports until attributes are accessed.
"""

from app.models.base import Base

__all__ = ["Base"]


def __getattr__(name: str):
    """
    Lazily load legacy aggregated model attributes to avoid circular imports during
    early DB setup (e.g., when app.core.database imports Base).
    """
    import importlib

    _registry = importlib.import_module("app.models.registry")

    if hasattr(_registry, name):
        return getattr(_registry, name)
    raise AttributeError(f"module 'app.models' has no attribute {name!r}")


def __dir__():
    import importlib

    _registry = importlib.import_module("app.models.registry")

    return sorted(set(list(globals().keys()) + list(_registry.__all__)))
