# Refactor Changelog

Record structural updates introduced during the re-architecture effort.

## 2025-11-06
- Added `app/core/`, `app/modules/`, and `app/integrations/` packages as the target layout for shared infrastructure, domain modules, and external adapters.
- Centralised router inclusion through `app/api/router.py`, trimming direct imports in `app/main.py`.
- Documented initial roadmap (`REARCHITECTURE_ROADMAP.md`) and module inventory snapshot.
- Extracted WebSocket connection management to `app/modules/notifications/realtime.py`
  with compatibility re-export from `app/notifications.py`.
- Moved email notification helpers to `app/modules/notifications/email.py` and wired
  `app/notifications.py` to depend on the modularised implementations.
- Split notification services, batching, analytics, and retry handlers into
  `app/modules/notifications/{service,analytics,batching}.py` with `app/notifications.py`
  now acting as a thin compatibility wrapper.
- Updated `app/routers/notifications.py` to reference the modularised services and
  analytics classes directly.
- Extracted notification-related Pydantic schemas to
  `app/modules/notifications/schemas.py` and re-exported them via `app/schemas.py`.
- Moved notification SQLAlchemy enums/models to
  `app/modules/notifications/models.py` and re-imported them in `app/models.py` for
  backwards compatibility.
- Extracted user domain enums, association tables, and models into
  `app/modules/users/models.py` with re-exports from `app/models.py`.
- Modularised utility helpers into `app/modules/utils/` (security, content, analytics,
  search, translation, etc.) while `app/utils.py` now acts as a compatibility facade.

## 2025-11-16
- Moved all comment-related Pydantic schemas (`Comment*`, `CommentStatistics`,
  `FlagCommentRequest`) into `app/modules/posts/schemas.py` and re-exported them from
  `app/schemas.py` to keep backwards compatibility while continuing the Phase 2
  schema split effort.
## 2025-11-17
- Completed the messaging slice of the schema partition by importing the canonical schemas from `app/modules/messaging/schemas.py`, removing the duplicate block from `app/schemas.py`, and keeping local wrappers only for legacy community helpers.
- Updated the modular `Message` schema to include the ORM `timestamp` column and to default `sticker_id` to `None` so `app.schemas.Message` stays compatible with existing API responses.
- Wired `MessageService` to call a router-level `scan_file_for_viruses` shim (delegating to `app.media_processing`) so the existing tests that patch `app.routers.message.scan_file_for_viruses` remain effective.
