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
- Runtime variables of note:
  - `APP_ENV` (`production`/`development`/`test`) controls heavy integrations (scheduler, Firebase, etc.).
  - `CORS_ORIGINS` (comma-separated) overrides the default origins served by `app/core/app_factory.py`.
  - `REDIS_URL` is optional; when not supplied the Redis features (search cache/autocomplete) degrade gracefully.

## Testing & Quality Gates
- Run unit tests: `python -m pytest -q`.
- Startup benchmark: `python scripts/perf_startup.py --iterations 3 --threshold 2.5`.
  - This script fails if the average startup time regresses—use it locally or wire into CI.
- New utility tests live under `tests/` (e.g., `tests/test_utils_search.py`, `tests/test_analytics_lazy.py`).
- CI: `.github/workflows/ci.yml` executes both `pytest` and the startup benchmark on pushes/PRs (with `APP_ENV=test` to bypass heavy integrations).

## Notes
- Background tasks are registered via `app/core/app_factory.py`. Keep `app/main.py` minimal.
- Health endpoints are exposed at `/livez` and `/readyz`. The readiness check performs a light DB query.
- WebSocket endpoints live under `app/api/websocket.py`.
- When adding dependencies that perform heavy initialization, ensure they load lazily to keep startup tests green.
- Migrations: use Alembic (`alembic revision --autogenerate -m "<msg>"` + `alembic upgrade head`). Keep generated migration files under version control.
- Secrets: never commit `.env`, Firebase credentials, RSA keys, or other sensitive files. Store them via environment variables or a secret manager.
