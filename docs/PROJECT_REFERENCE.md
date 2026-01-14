# Project Reference (Unified)

Single-source reference for architecture, developer guidance, documentation style, changelog, and roadmap.

## Documentation Map
- `docs/REPO_REFERENCE.md`: full file index with one-line summaries per module/file.
- `docs/API_REFERENCE.md`: router/endpoint inventory generated from route decorators.
- `docs/DATA_MODEL.md`: domain-level data model overview and relationships.
- `docs/FEATURE_FLOWS.md`: end-to-end feature workflows (auth, content, moderation, business, support, AI).
- `docs/TESTS_REFERENCE.md`: test-suite index with module-level summaries.
- `docs/SCALABILITY.md`: scaling roadmap and decomposition signals.

## Architecture Map
- **app/**: core config (settings, DB, cache, logging, monitoring, middleware, app factory), API aggregation, routers, domain modules (users, community, posts, notifications, messaging, moderation, search, media, utils, social, marketplace, learning, local_economy, collaboration, wellness, amenhotep), services, integrations, AI chat, compatibility shims, models/schemas, Celery worker, entrypoint.
- **alembic/**: migration environment and versioned scripts.
- **scripts/**: CLI helpers (perf benchmarks, DB checks, backups, subclass checks, locust load tests).
- **docs/**: guides, dashboards, and this reference.
- **monitoring/**: Prometheus/Grafana configs and dashboards.
- **k8s/**: Kubernetes manifests (app, Redis, Postgres, HPA).
- **static/**: served assets (legal docs, sample files).
- **tests/**: pytest suite for routers/services/security/caching/monitoring/notifications/search/e2e; see `tests/README.md`.
- **go/**: optional realtime gateway (Redis-backed WebSocket fanout).
- **rust/**: optional PyO3 extension for social economy scoring helpers.
- **ops**: Dockerfile, docker-compose, Procfile, requirements, README, .env example.

## Developer Guide
### Architecture Overview
- **Core**: shared concerns under `app/core` (config, database, middleware, scheduling, app factory).
- **Modules**: domain-specific packages under `app/modules/**` (models, schemas, services, helpers).
- **Routers**: thin FastAPI routers in `app/routers` depending on services/schemas.
- **Services**: business logic in `app/services/**` to keep routers slim.
- **Notifications**: canonical implementations live in `app/modules/notifications/**`; `app/notifications.py` is a compatibility shim for legacy imports.

### Adding a New Feature
1. Define models/schemas in the relevant module (or create a new one under `app/modules`).
2. Implement business logic in `app/services/<domain>/`.
3. Add a router in `app/routers` importing only needed services/schemas.
4. Register the router in `app/api/router.py`.

### Configuration & Database
- Import settings from `app.core.config` and DB sessions via `app.core.database.get_db`.
- Key env vars: `APP_ENV`, `CORS_ORIGINS`, `ALLOWED_HOSTS`, `FORCE_HTTPS`, `STATIC_ROOT`/`UPLOADS_ROOT` (+ cache headers), `REDIS_URL` (optional, degrades gracefully), DB URLs (`DATABASE_URL`/`TEST_DATABASE_URL`), RSA key paths (auto-generated in dev/test when missing) or `RSA_PRIVATE_KEY`/`RSA_PUBLIC_KEY` to write key files at startup.
- Migrations: `alembic revision --autogenerate -m "<msg>"` + `alembic upgrade head`.

### Testing & Quality Gates
- `python -m pytest -q`
- Startup benchmark: `python scripts/perf_startup.py --iterations 3 --threshold 2.5`
- CI runs pytest + startup check (`APP_ENV=test`).
- Pre-commit: `pip install pre-commit && pre-commit install && pre-commit run --all-files`.

### Notes
- Background tasks registered via `app/core/app_factory.py`; keep `app/main.py` minimal.
- Health endpoints: `/livez` (liveness), `/readyz` (DB/Redis readiness).
- WebSockets: notification socket in `app/api/websocket.py`; call signaling under `/ws/call/{room_id}`.
- Heavy deps should load lazily to keep startup tests green.
- Secrets: never commit `.env`, Firebase creds, RSA keys; use env/secret manager.

### Amenhotep AI (ONNX)
- Model: `aubmindlab/bert-base-arabertv02`; uses ONNX if `AMENHOTEP_ONNX_PATH` exists, else PyTorch.
- Export helper: `AmenhotepAI.export_to_onnx()` writes to `data/amenhotep/amenhotep.onnx`.
- Embeddings cached with TTL/max size to avoid recomputation.
- Arabic prompts are answered in Modern Standard Arabic; verified facts are summarized when a DB session is available.

### WebRTC Signaling (Calls)
- Endpoint: `GET /ws/call/{room_id}?token=<join_token>` with JWT auth.
- First joiner is owner; can mint single-use join tokens. Rooms expire (default 1h).
- Messages forwarded to other participants; registry mirrored to Redis (`callroom:{room_id}`) when available.

## Documentation & Commenting Style
- Clarity over verbosity; document intent, contracts, side effects, edge cases.
- Docstrings (Google-style) for public functions/classes in core/services/routers/modules; include `Args/Returns/Raises` where relevant. Module docstrings summarize scope and invariants.
- Inline comments are rare, reserved for non-obvious logic, performance/security constraints, or compatibility shims.
- Tests: descriptive names; brief comments only for tricky fixtures/mocks/timeouts.
- Keep prose in English, line lengths reasonable, ASCII unless existing content requires otherwise.
- Coverage status: core app factory/config/logging/telemetry/monitoring, middleware, database, cache/scheduling, auth (oauth2/crypto/sessions/2FA/social/OAuth), API aggregation (HTTP/WS), domain routers/services (notifications, messaging/calls/screen share, community, posts/comments/reactions/reels, search/Typesense, support/wellness/collaboration/impact), AI (Amenhotep), utilities, and model registry now have concise docstrings describing scope, auth expectations, cache/side effects, and fail-open behavior. Prefer importing from modular packages; compatibility shims remain documented for legacy imports.

## Review/CI Checklist
- Docstrings present on public APIs (core/services/routers/modules); models/enums/schemas documented when behavior is non-trivial.
- FastAPI endpoints state auth/permissions, rate limits, side effects (DB writes, cache invalidation), and error modes; WebSockets describe handshake/auth/message shapes.
- Lifecycle/infra documented: app factory, middleware ordering, cache/monitoring, scheduling/Celery behavior, env/secret expectations.
- Inline comments are concise and only where needed; matches the style above.
- Caching/search: cache keys/invalidations noted; fail-open behavior understood.
- Tests: complex fixtures/mocks/time-sensitive tests clarified when necessary.
- Ops: background jobs documented (Celery/APScheduler), observability endpoints `/metrics`, `/livez`, `/readyz`, logging rotation/JSON options.

## Refactor Changelog
### 2025-11-06
- Added `app/core/`, `app/modules/`, and `app/integrations/` packages as the target layout for shared infrastructure, domain modules, and external adapters.
- Centralised router inclusion through `app/api/router.py`, trimming direct imports in `app/main.py`.
- Documented initial roadmap and module inventory snapshot.
- Extracted WebSocket connection management to `app/modules/notifications/realtime.py` with compatibility re-export from `app/notifications.py`.
- Moved email notification helpers to `app/modules/notifications/email.py` and wired `app/notifications.py` to depend on the modularised implementations.
- Split notification services, batching, analytics, and retry handlers into `app/modules/notifications/{service,analytics,batching}.py` with `app/notifications.py` now acting as a thin compatibility wrapper.
- Updated `app/routers/notifications.py` to reference the modularised services and analytics classes directly.
- Extracted notification-related Pydantic schemas to `app/modules/notifications/schemas.py` and re-exported them via `app/schemas.py`.
- Moved notification SQLAlchemy enums/models to `app/modules/notifications/models.py` and re-imported them in `app/models.py` for backwards compatibility.
- Extracted user domain enums, association tables, and models into `app/modules/users/models.py` with re-exports from `app/models.py`.
- Modularised utility helpers into `app/modules/utils/` while `app/utils.py` acts as a compatibility facade.

### 2025-11-16
- Moved all comment-related Pydantic schemas into `app/modules/posts/schemas.py` and re-exported them from `app/schemas.py` to keep backwards compatibility during the schema split.

### 2025-11-17
- Completed the messaging slice of the schema partition by importing canonical schemas from `app/modules/messaging/schemas.py`, removing the duplicate block from `app/schemas.py`, and keeping local wrappers only for legacy community helpers.
- Updated the modular `Message` schema to include the ORM `timestamp` column and to default `sticker_id` to `None` so `app.schemas.Message` stays compatible with existing API responses.
- Wired `MessageService` to call a router-level `scan_file_for_viruses` shim so existing tests that patch `app.routers.message.scan_file_for_viruses` remain effective.

### 2025-12-22
- Centralised SQLAlchemy `Base` in `app/models/base.py` and wired `app.core.database`/Alembic to consume the shared base.
- Cleaned module exports so `app.modules.users` and `app.modules.notifications` re-export their models and services for direct imports.
- Moved community `Category`/`Tag` schemas into `app/modules/community/schemas.py` and dropped the legacy duplicates in `app/schemas.py`.
- Converted `app.models` into a package with a lazy registry to prevent circular imports while keeping legacy model re-exports.
- Added DB integrity indexes/constraints (follows and search statistics) with Alembic migration, and a CI helper `scripts/check_migrations.py` to validate upgrades on a clean database.
- Security QA additions: tests covering cross-user comment edits and restricted block appeal access to enforce permissions.
- Performance: added bulk post scoring in `SocialEconomyService`, polars-backed analytics charting, and `scripts/perf_api_latency.py` for latency benchmarking.
- Caching: TTL overrides + compression, stampede protection for cache decorator, and post cache invalidation hooks in post service.
- Realtime: connection registry now tracks socket counts; added authenticated call signaling WebSocket router and integrated it into API routing.

### 2025-12-25
- Documentation sweep: added module/class docstrings across core app factory, middleware, cache, search, AI, notifications, messaging, and services; consolidated reference into this document.
- README expansions: environment loading/secrets, logging rotation/JSON, background jobs, static/uploads hosting, optional AI setup, WebSocket auth, and ops runbook for migrations/cache/workers/observability.
- Tests: added `tests/README.md` summarizing fixtures/env defaults and notable suites; clarified monitoring/cache guard behavior.

## Next Steps
- Retire compatibility shims (`app/notifications.py`, `app/utils.py`) after imports migrate to modular packages; delete shims once downstream usages are updated.
- Decide the fate of social media publishing: either reintroduce a maintained router or drop the unused models/fields that only serve the placeholder integration.
- Expand coverage for newly added admin/moderation/support workflows and WebSocket edge cases to reduce regression risk.
- Keep dependency hygiene tight: review Dependabot alerts weekly and run a periodic `pip-audit`/`pip list --outdated` pass before releases.

## Documentation Roadmap (Completed)
- Phases 1–22 executed covering inventory, style, DB layer, logging/monitoring, errors/middleware, security/auth, cache/Redis, scheduling/Celery, API/WebSockets, domain models/services/routers, notifications/realtime, messaging/calls, search/caching, media/content safety, AI, static assets, testing/quality gates, operations/runbooks, and final audit.

## Testing Overview
- See `tests/README.md` for fixtures, env defaults (APP_ENV=test), SQLite fallback, Redis optionality, and notable suites (caching/monitoring, notifications, scheduling).
