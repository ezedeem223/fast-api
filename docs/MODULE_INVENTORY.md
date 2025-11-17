# Module Inventory (Phase 1 Snapshot)

| Area | Location | Responsibilities | Notes |
|------|----------|------------------|-------|
| Application entry | `app/main.py` | App factory, middleware, router registration, startup jobs | Router aggregation now delegated to `app/api/router.py`. |
| API routing | `app/api/router.py`, `app/routers/` | HTTP endpoints per feature domain | Needs slimming once services extracted. |
| Data models | `app/models.py` | All SQLAlchemy models and enums | Monolithic; scheduled for partitioning in Phase 2. |
| Schemas | `app/schemas.py` | Pydantic DTOs across features | Mirrors `models.py`, also slated for split. |
| Notifications | `app/notifications.py`, `app/modules/notifications/`, `app/modules/notifications/schemas.py`, `app/modules/notifications/models.py`, `app/routers/notifications.py` | Notification services, delivery adapters, data models, API endpoints, and schemas | Domain partition underway; shared facade remains in `app/notifications.py` while feature modules reside under `app/modules/notifications/`. |
| Users | `app/modules/users/models.py`, `app/modules/users/__init__.py`, `app/models.py` (compat imports) | Core user models, enums, association tables | `app/models.py` re-exports while full definitions live under `app/modules/users/`. |
| Utilities | `app/utils.py`, `app/modules/utils/` | Authentication, content moderation, storage, analytics, search, translation helpers | `app/utils.py` now re-exports from modular subpackages for backwards compatibility. |
| Utilities | `app/utils.py` | Mixed helpers (auth, content, analytics, ML) | Will be split into focused modules. |
| Configuration | `app/config.py`, `.env` | Settings management and external service credentials | To migrate under `app/core/config/`. |
| Database | `app/database.py` | Engine/session management | Ready for relocation into core package. |
| Background tasks | `app/celery_worker.py`, APScheduler usage in `app/main.py` | Async processing | Requires consolidation under `app/core/scheduling`. |
| Tests | `tests/` | Pytest functional coverage | Must be updated to reflect module moves. |

> This table will evolve as modules are migrated. Update after each major refactor.
