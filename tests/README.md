# Tests Overview

## Environments
- Default test env: set `APP_ENV=test` to disable heavy services (schedulers, Celery eager mode, Redis optional).
- Database: tests require Postgres and a dedicated `_test` database; set `LOCAL_TEST_DATABASE_URL` or `TEST_DATABASE_URL` (or configure `DATABASE_URL`/`DATABASE_*` so tests derive a `_test` DB).
- SQLite option: set `PYTEST_SQLITE=1` to run tests against `sqlite:///./tests/pytest_sqlite.db` (best-effort, may not cover every Postgres-only path).
- Redis: optional; many cache tests use fakes/stubs and fail open when Redis is absent.
- Seeded users: tests pre-create a small batch of users to satisfy FK-heavy fixtures; override with `TEST_SEED_USER_COUNT` (set to `0` to disable).
- Cleanup strategy: set `TEST_DB_CLEAN_STRATEGY=truncate|delete` to override; remote DBs default to `delete` to avoid long `TRUNCATE` locks.

## Fixtures & Patterns
- Common fixtures live in `tests/conftest.py` and `tests/database.py`; they provide DB sessions and client setup.
- WebSocket tests allow tokenless connections when `APP_ENV=test` to simplify fixtures.
- Background tasks/schedulers are guarded to avoid lingering threads during tests.

## Structure
- Domain suites live under `tests/` subfolders (e.g., `tests/auth`, `tests/community`, `tests/content`, `tests/notifications`, `tests/search`).
- Platform/core checks live under `tests/core` (app factory, settings, middleware, scheduling, cache/database helpers).
- Cross-cutting flows live under `tests/flows`.
- External integrations live under `tests/integrations`.

## Notable Test Areas
- Caching/Monitoring: `tests/core/test_monitoring_and_redis_cache.py` covers metrics setup guard and Redis cache behaviors.
- Notifications: suites under `tests/notifications` cover service/retry/batching and WebSocket messaging; Celery runs in eager mode under tests.
- Scheduling: tests under `tests/core` avoid running APScheduler in test env; repeat_every helpers no-op when `APP_ENV=test`.

## Quality Gates
- `pytest -q` runs unit/integration tests; `scripts/perf_startup.py` is used to catch startup regressions.
- Docstring coverage and style are enforced during reviews; follow `docs/DOCS_STYLE_GUIDE.md` and `docs/DOCS_CI_CHECKLIST.md`.

## Index
- File-level test index: `docs/TESTS_REFERENCE.md`
