# FastAPI Social Platform

A modular FastAPI backend that powers social features such as posts, reels/stories,
messaging, notifications, and moderation workflows. Code is organized under `app/`
into core config, domain modules, services, and routers to keep each concern
isolated and testable.

## Requirements
- Python 3.11+ (3.12 tested)
- Postgres 13+ (required)
- Redis 6+ (required for Celery/realtime; optional for API-only runs)
- Optional: Go 1.21+ (realtime gateway), FFmpeg (media processing), Rust (maturin)

## Getting Started
```bash
python -m venv venv
# Windows
.\venv\Scripts\activate
# Linux/macOS
# source venv/bin/activate

pip install -r requirements.txt
cp .env.example .env
```

Edit `.env` with your local settings (DB, Redis, secrets).

## Run Locally
```bash
alembic upgrade head
uvicorn app.main:app --reload
```

Optional worker/beat (Celery):
```bash
celery -A app.celery_worker.celery_app worker -B -l info
```

Optional realtime gateway (Go):
```bash
cd go/realtime
go run main.go
```

Optional social economy extension (Rust): see `rust/social_economy/README.md`
for build steps and maturin integration.

## Configuration
Full list is in `.env.example`. Minimal local values:
```bash
APP_ENV=development
DATABASE_URL=postgresql+psycopg2://user:pass@localhost:5432/app_db
TEST_DATABASE_URL=postgresql+psycopg2://user:pass@localhost:5432/app_db_test
REDIS_URL=redis://localhost:6379/0
SECRET_KEY=change-me
REFRESH_SECRET_KEY=change-me
REFRESH_ALGORITHM=HS256
REFRESH_TOKEN_EXPIRE_MINUTES=10080
RSA_PRIVATE_KEY_PATH=./private_key.pem
RSA_PUBLIC_KEY_PATH=./public_key.pem
OTP_ENCRYPTION_KEY=change-me
```

Key environment variables:
- `APP_ENV` (`production`/`development`/`test`) toggles heavy integrations.
- `DATABASE_URL` / `TEST_DATABASE_URL` control SQLAlchemy connections.
- `REDIS_URL` powers caching, Celery broker/backend, and realtime fanout.
- `ALLOWED_HOSTS` and `CORS_ORIGINS` control allowed hosts and CORS origins.
- `FORCE_HTTPS` enables HTTPS redirects in production.
- `STATIC_ROOT` / `UPLOADS_ROOT` set static and upload directories.
- `REFRESH_SECRET_KEY` / `REFRESH_ALGORITHM` / `REFRESH_TOKEN_EXPIRE_MINUTES` govern refresh tokens.
- `OTP_ENCRYPTION_KEY` encrypts OTP secrets at rest.
- `JWT_KEY_ID` / `JWT_PRIVATE_KEYS` / `JWT_PUBLIC_KEYS` enable JWT key rotation and JWKS.
- `GLOBAL_RATE_LIMIT` sets the app-wide default rate limit (per IP).
- `PASSWORD_STRENGTH_REQUIRED` / `PASSWORD_STRENGTH_MIN_SCORE` enforce password strength.
- `REALTIME_REDIS_URL` / `REALTIME_REDIS_CHANNEL` let FastAPI publish to the Go gateway.

### Environment loading & secrets
- `.env` in the repo root is loaded first, then process env overrides it.
- Databases: prefer `DATABASE_URL`; for tests use `TEST_DATABASE_URL` or a `_test` DB.
- Crypto: `RSA_PRIVATE_KEY_PATH` / `RSA_PUBLIC_KEY_PATH` must point to non-empty files; set `RSA_PRIVATE_KEY` / `RSA_PUBLIC_KEY` to write them at startup; in `APP_ENV=development|test`, missing keys are generated automatically.
- Redis: required for Celery/realtime; if unset the API still starts with cache disabled.

### Logging
- Defaults: console logging; set `LOG_DIR` for file rotation.
- JSON logs: set `USE_JSON_LOGS=true` for aggregation platforms.

### Background jobs
- Celery worker + beat uses Redis by default (in-memory eager mode in tests).
- APScheduler/repeat_every tasks run only outside tests.

### Realtime gateway (Go)
- Env: `REDIS_URL`, `REDIS_CHANNEL` (default `realtime:broadcast`), `BIND_ADDR` (default `:8081`).
- FastAPI can publish to the gateway via `REALTIME_REDIS_URL` / `REALTIME_REDIS_CHANNEL`.

### Optional AI (Amenhotep)
- Model: `aubmindlab/bert-base-arabertv02`; ONNX if `AMENHOTEP_ONNX_PATH` exists.
- Export to ONNX: `python scripts/export_amenhotep_onnx.py --out data/amenhotep/amenhotep.onnx`.

### Static & uploads
- Static files served from `STATIC_ROOT` at `/static`; uploads from `UPLOADS_ROOT` at `/uploads`.
- Cache headers set via `STATIC_CACHE_CONTROL` / `UPLOADS_CACHE_CONTROL`.

### Operations (Docker/Compose)
- `Dockerfile` builds a slim runtime image.
- Local stack: `docker compose up --build` (API + Postgres + Redis + Celery worker).
- Monitoring stack: `docker compose -f docker-compose.yml -f docker-compose.monitoring.yml up --build`
  starts Prometheus + Grafana.
- Legacy: `docker-compose-dev.yml` and `docker-compose-prod.yml` are retained for
  backwards compatibility.

### Monitoring
- `/metrics` is available when `ENABLE_METRICS=1`.
- Prometheus scrapes `api:8000/metrics` (see `monitoring/prometheus.yml`).
- Grafana is pre-provisioned with a dashboard (`monitoring/grafana/dashboards/fastapi.json`).
  Default login: `admin` / `admin` (change for shared environments).

### Kubernetes
- Manifests live in `k8s/` and are applied via `kubectl apply -k k8s`.
- Update `k8s/api-configmap.yaml` and `k8s/api-secrets.yaml` before deploying.
- `k8s/postgres-statefulset.yaml` and `k8s/redis-deployment.yaml` are for dev/test clusters;
  use managed services in production.

## Running & Quality Gates
```bash
pytest -q
python scripts/perf_startup.py
```

Pre-commit (optional):
```bash
pip install pre-commit
pre-commit install
pre-commit run --all-files
```

## Continuous Integration
GitHub Actions runs linting, pytest, and startup smoke tests with `APP_ENV=test`.

## Security & Edge Protection
- Deploy behind a WAF/CDN and restrict `ALLOWED_HOSTS`.
- `/livez` and `/readyz` are health checks for load balancers.
- JWT auth uses RSA keys; WebSocket auth requires a valid token in production.
- JWKS is available at `/jwks.json` for public key discovery.
- Rate limits apply globally and on selected endpoints (e.g., posts, uploads).

## Documentation
- Full project reference: `docs/PROJECT_REFERENCE.md`
- Scalability roadmap: `docs/SCALABILITY.md`
- Repository file index: `docs/REPO_REFERENCE.md`
- API inventory: `docs/API_REFERENCE.md`
- Data model overview: `docs/DATA_MODEL.md`
- Feature flows: `docs/FEATURE_FLOWS.md`
- Tests index: `docs/TESTS_REFERENCE.md`
- Native components: `go/realtime/README.md`, `rust/social_economy/README.md`

Contributions should follow the module/service/router structure and include tests
when behavior changes.
