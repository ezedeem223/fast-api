# Developer Guide

## Architecture Overview
- **Core**: shared concerns under `app/core` (config, database, middleware, scheduling, app factory).
- **Modules**: domain-specific packages (`app/modules/users`, `posts`, `notifications`, etc.) containing models, schemas, services, and helpers.
- **Routers**: thin FastAPI routers inside `app/routers` which depend on module services.
- **Services**: business logic in `app/services/**` to keep routers slim.

## Adding a New Feature
1. Define domain models/schemas inside an appropriate module or create a new module in `app/modules`.
2. Implement business logic in `app/services/<domain>/`.
3. Create a router in `app/routers` that imports only the necessary services/schemas.
4. Register the router via `app/api/router.py` so it becomes part of the aggregated API.

## Configuration & Database
- Always import settings from `app.core.config` (`from app.core.config import settings`).
- Use `app.core.database.get_db` inside routers/services for session injection.

## Testing & Quality Gates
- Run unit tests: `python -m pytest -q`.
- Startup benchmark: `python scripts/perf_startup.py --iterations 3 --threshold 2.5`.
  - This script fails if the average startup time regresses—use it locally or wire into CI.
- New utility tests live under `tests/` (e.g., `tests/test_utils_search.py`, `tests/test_analytics_lazy.py`).

## Notes
- Background tasks are registered via `app/core/app_factory.py`. Keep `app/main.py` minimal.
- WebSocket endpoints live under `app/api/websocket.py`.
- When adding dependencies that perform heavy initialization, ensure they load lazily to keep startup tests green.
