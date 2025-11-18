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

## Documentation

- docs/DEVELOPER_GUIDE.md contains architecture notes, configuration tips, and testing requirements.
- REARCHITECTURE_ROADMAP.md tracks the phased refactor/feature plan.

Contributions should follow the module/service/router structure and include tests whenever behaviour changes.
