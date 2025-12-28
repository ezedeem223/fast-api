# FastAPI Social Platform

A modular FastAPI backend that powers social features such as posts, reels/stories, group messaging, notifications, and moderation workflows. Code is organised under pp/ into core config, domain modules, services, and routers so each concern stays isolated and testable.

## Getting Started

`ash
python -m venv venv
source venv/bin/activate  # or .\\venv\\Scripts\\activate on Windows
pip install -r requirements.txt
cp .env.example .env  # provide secrets like DATABASE_URL, REDIS_URL, etc.
`

Key environment variables:
- `APP_ENV` (`production`/`development`/`test`) toggles heavy integrations.
- `DATABASE_URL` / `TEST_DATABASE_URL` control SQLAlchemy connections.
- `REDIS_URL`, `CORS_ORIGINS`, `FRONTEND_BASE_URL` tune caching and API boundaries.
- `ALLOWED_HOSTS` comma-separated allowlist for `TrustedHostMiddleware` (default `*`).
- `FORCE_HTTPS` (bool) enables `HTTPSRedirectMiddleware` in production.
- `STATIC_ROOT` / `UPLOADS_ROOT` determine on-disk static + user-upload dirs mounted at `/static` and `/uploads`; corresponding `STATIC_CACHE_CONTROL` / `UPLOADS_CACHE_CONTROL` headers control browser caching.
- `FACEBOOK_APP_ID` / `FACEBOOK_APP_SECRET` and `TWITTER_API_KEY` / `TWITTER_API_SECRET` configure the additional OAuth providers exposed under `/auth/facebook` and `/auth/twitter`.

### Environment loading & secrets
- Precedence: `.env` at the repo root is loaded first, then process environment variables override it.
- Databases: prefer `DATABASE_URL`; for tests use `TEST_DATABASE_URL` or `_test`-suffixed DB names.
- Crypto: `RSA_PRIVATE_KEY_PATH` / `RSA_PUBLIC_KEY_PATH` resolve relative to the repo root when not absolute and must point to non-empty files.
- Redis: `REDIS_URL` enables caching; if unset or unreachable the app degrades gracefully with cache disabled.
- HTTPS/hosts: `FORCE_HTTPS` defaults to true in production when unset; set `ALLOWED_HOSTS` (JSON or comma list) to restrict hosts behind your edge/WAF.

### Logging
- Defaults: console logging with colors; rotation to `logs/` when `LOG_DIR` is set (see `.env.example`).
- JSON logs: enable via `USE_JSON_LOGS=true` for aggregation platforms; files rotate at 10MB with 5 backups.
- Context: request logs include `request_id`, `user_id`, and `ip` when available via middleware.

### Background jobs
- Celery worker + beat: uses Redis (or in-memory/eager in tests) for notifications, bans, content checks, and scheduled posts.
- APScheduler + repeat_every tasks: run only outside tests; cover search suggestions, post score recalculation, notification cleanup/retry.
- Keep `APP_ENV=test` for local CI-style runs to avoid starting long-lived schedulers.

### Realtime gateway (Go)
- A lightweight Go WebSocket bridge lives in `go/realtime` and fans out messages received on Redis pub/sub to connected clients.
- Env: `REDIS_URL` (default `redis://localhost:6379/0`), `REDIS_CHANNEL` (default `realtime:broadcast`), `BIND_ADDR` (default `:8081`).
- Run locally: `cd go/realtime && go run main.go`.
- FastAPI can publish to the bridge by setting `REALTIME_REDIS_URL` / `REALTIME_REDIS_CHANNEL` (see notifications realtime sender).

### Optional AI (Amenhotep)
- Model: `aubmindlab/bert-base-arabertv02`; prefers ONNX runtime if `AMENHOTEP_ONNX_PATH` exists, otherwise uses PyTorch.
- Cache: embeddings cached with TTL/size bounds to reduce recomputation.
- Data: knowledge base loaded from `data/amenhotep/knowledge_base.json` when present.
- Export to ONNX: `python scripts/export_amenhotep_onnx.py --out data/amenhotep/amenhotep.onnx` (requires torch/transformers/onnxruntime).

### Static & uploads
- Static files served from `STATIC_ROOT` (default `static/`) at `/static`; uploads from `UPLOADS_ROOT` at `/uploads`.
- Cache-Control headers set via `STATIC_CACHE_CONTROL` / `UPLOADS_CACHE_CONTROL`; review before hosting sensitive files.
- Terms/privacy or other legal docs under `static/` are served as-is; consider CDN caching/invalidations as needed.

### Operations (Docker/Compose)
- `Dockerfile` builds a slim runtime image; `docker-compose-dev.yml` mounts source read-only with hot reload for dev.
- Set secrets via environment or mounted `.env`; never bake keys into the image (RSA keys resolved relative to repo).
- For production, ensure Redis/Postgres endpoints are reachable; set `FORCE_HTTPS=true` and tighten `ALLOWED_HOSTS`.

## Running & Quality Gates

`ash
python -m pytest -q             # unit/integration tests
python scripts/perf_startup.py  # startup regression guard
`

Static checks are enforced locally through pre-commit:
`ash
pip install pre-commit
pre-commit install
pre-commit run --all-files  # optional before pushing
`

## Continuous Integration

GitHub Actions workflow (.github/workflows/ci.yml) runs on pushes/pull-requests to main. It installs dependencies, executes Ruff linting, pytest, and the startup smoke test with APP_ENV=test so heavy services (Firebase, schedulers) stay disabled.

## Security & Edge Protection

- Deploy the API behind a WAF/CDN (e.g., Cloudflare, Azure FrontDoor). Combine the edge allowlist with the `ALLOWED_HOSTS` and `FORCE_HTTPS` flags to restrict origins and force TLS end-to-end.
- `/livez` and `/readyz` are lightweight health checks that can be used by your load balancer/WAF to decide when to route traffic.
- Auth & sessions: JWTs are RSA-signed; sessions can be revoked/blacklisted via session endpoints. IP bans are enforced in non-test environments.
- Rate limits: enforced via slowapi where decorators are applied (e.g., posts, polls, uploads).
- Blocking/bans: moderation models support user/IP bans; requests from banned IPs are short-circuited early in middleware.
- WebSocket auth: `/ws/{user_id}` requires a valid JWT matching the path user in production; test contexts allow tokenless for fixtures. Messages are forwarded to the user via the notifications manager.

## Operations Runbook
- **Migrations**: `alembic upgrade head` (ensure `ALEMBIC_DATABASE_URL` or `DATABASE_URL` is set). Generate via `alembic revision --autogenerate -m "msg"`.
- **Cache/queues**: Redis is optional; when available, it powers caching and Celery broker/backend. If Redis is down, cache gracefully disables; ensure broker is reachable before starting workers.
- **Workers**: start Celery worker + beat (`celery -A app.celery_worker.celery_app worker -B`) after DB is ready. In tests/CI, Celery runs eager/in-memory.
- **Observability**: `/metrics` (Prometheus), `/livez` (liveness), `/readyz` (DB/Redis readiness). Logs rotate in `LOG_DIR` when set; enable `USE_JSON_LOGS` for aggregation.
- **Rust acceleration**: a PyO3 crate under `rust/social_economy` exposes `social_economy_rs`; build via `maturin develop` and the `SocialEconomyService` will dispatch scoring to Rust if the extension is present.

## Documentation

- Full project reference (architecture, style, changelog, roadmap): `docs/PROJECT_REFERENCE.md`

Contributions should follow the module/service/router structure and include tests whenever behaviour changes.
