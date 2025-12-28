# Tests Overview

## Environments
- Default test env: set `APP_ENV=test` to disable heavy services (schedulers, Celery eager mode, Redis optional).
- Database: tests default to SQLite (`test.db`) unless `TEST_DATABASE_URL` is provided; ensures `_test` suffix for safety.
- Redis: optional; many cache tests use fakes/stubs and fail open when Redis is absent.

## Fixtures & Patterns
- Common fixtures live in `tests/conftest.py` and `tests/database.py`; they provide DB sessions and client setup.
- WebSocket tests allow tokenless connections when `APP_ENV=test` to simplify fixtures.
- Background tasks/schedulers are guarded to avoid lingering threads during tests.

## Notable Test Areas
- Caching/Monitoring: `tests/test_monitoring_and_redis_cache.py` covers metrics setup guard and Redis cache behaviors.
- Notifications: multiple suites cover service/retry/batching and WebSocket messaging; Celery runs in eager mode under tests.
- Scheduling: tests avoid running APScheduler in test env; repeat_every helpers no-op when `APP_ENV=test`.

## Quality Gates
- `pytest -q` runs unit/integration tests; `scripts/perf_startup.py` is used to catch startup regressions.
- Docstring coverage and style are enforced during reviews; follow `docs/DOCS_STYLE_GUIDE.md` and `docs/DOCS_CI_CHECKLIST.md`.
