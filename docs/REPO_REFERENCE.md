# Repository Reference (Detailed)

Full file index with module-level summaries. This complements `docs/PROJECT_REFERENCE.md`.

## app/

### Top-level files
- `app/__init__.py` - App package init.
- `app/analytics.py` - Analytics helpers for sentiment, search stats, and conversation metrics.
- `app/cache.py` - App module: cache.
- `app/celery_worker.py` - Celery worker configuration and tasks.
- `app/content_filter.py` - App module: content_filter.
- `app/crypto.py` - App module: crypto.
- `app/firebase_config.py` - Firebase initialization and notification helpers with graceful failure logging.
- `app/i18n.py` - App module: i18n.
- `app/link_preview.py` - Link preview extractor with HTML parsing; degrades gracefully on errors.
- `app/main.py` - Application entrypoint that delegates to the app factory.
- `app/media_processing.py` - Compatibility shim for media processing utilities.
- `app/moderation.py` - Compatibility shim for moderation services.
- `app/notifications.py` - Compatibility facade for the modularised notifications domain.
- `app/oauth2.py` - JWT utilities for auth and session enforcement.
- `app/schemas.py` - File: schemas.py

### app/api/
- `app/api/__init__.py` - API router aggregation utilities.
- `app/api/router.py` - Centralized API router registration with feature grouping.
- `app/api/websocket.py` - WebSocket endpoints for real-time notifications.

### app/ai_chat/
- `app/ai_chat/amenhotep.py` - Amenhotep AI chat with ONNX acceleration and embedding cache.

### app/core/
- `app/core/__init__.py` - Core infrastructure package.
- `app/core/app_factory.py` - Application factory helpers to keep app/main.py lightweight.
- `app/core/cache/redis_cache.py` - Redis cache facade with graceful degradation.
- `app/core/config/__init__.py` - Core configuration package.
- `app/core/config/environment.py` - Environment-aware settings loader.
- `app/core/config/settings.py` - Application settings loaded from environment with safe fallbacks and keyfile validation.
- `app/core/database/__init__.py` - Core database access helpers with optimized connection pooling.
- `app/core/database/query_helpers.py` - Query optimization helpers for eager loading and pagination.
- `app/core/database/session.py` - Database engine and session management utilities.
- `app/core/db_defaults.py` - Database-aware helpers for SQL column defaults.
- `app/core/error_handlers.py` - Global exception handlers with unified response shape.
- `app/core/exceptions.py` - Custom Exception Classes for the Application
- `app/core/logging_config.py` - Logging configuration.
- `app/core/middleware/__init__.py` - Core application middleware utilities.
- `app/core/middleware/headers.py` - Response header middleware.
- `app/core/middleware/ip_ban.py` - IP ban middleware.
- `app/core/middleware/language.py` - Language-aware HTTP middleware.
- `app/core/middleware/logging_middleware.py` - Logging middleware for FastAPI.
- `app/core/middleware/rate_limit.py` - Rate limiting utilities.
- `app/core/monitoring.py` - Prometheus monitoring configuration with duplicate-registration guard.
- `app/core/scheduling/__init__.py` - Scheduling utilities for application startup tasks.
- `app/core/scheduling/tasks.py` - Centralised scheduling and startup task registration.
- `app/core/telemetry.py` - Lightweight telemetry wiring (OpenTelemetry + optional Sentry).

### app/integrations/
- `app/integrations/__init__.py` - Integration adapters for external services (e.g., Firebase, email, third-party APIs).

### app/models/
- `app/models/__init__.py` - Lightweight models package initialiser.
- `app/models/base.py` - Shared SQLAlchemy declarative base for all ORM models.
- `app/models/registry.py` - Aggregated model exports kept for legacy import paths.

### app/modules/
#### app/modules/
- `app/modules/__init__.py` - Domain modules namespace.

#### app/modules/amenhotep/
- `app/modules/amenhotep/__init__.py` - Amenhotep domain exports for chatbot conversations and edit history tracking.
- `app/modules/amenhotep/models.py` - Amenhotep AI chat models and helpers.

#### app/modules/collaboration/
- `app/modules/collaboration/__init__.py` - collaboration package exports.
- `app/modules/collaboration/models.py` - Collaboration domain models.
- `app/modules/collaboration/schemas.py` - collaboration schemas.

#### app/modules/community/
- `app/modules/community/__init__.py` - Community domain exports.
- `app/modules/community/associations.py` - Association tables for the community domain.
- `app/modules/community/models.py` - Community domain SQLAlchemy models and enums.
- `app/modules/community/schemas.py` - Community domain Pydantic schemas.

#### app/modules/fact_checking/
- `app/modules/fact_checking/__init__.py` - fact_checking package exports.
- `app/modules/fact_checking/models.py` - fact_checking domain models.
- `app/modules/fact_checking/service.py` - fact_checking domain services.

#### app/modules/learning/
- `app/modules/learning/__init__.py` - learning package exports.
- `app/modules/learning/models.py` - learning domain models.

#### app/modules/local_economy/
- `app/modules/local_economy/__init__.py` - local_economy package exports.
- `app/modules/local_economy/models.py` - local_economy domain models.

#### app/modules/marketplace/
- `app/modules/marketplace/__init__.py` - marketplace package exports.
- `app/modules/marketplace/models.py` - marketplace domain models.

#### app/modules/media/
- `app/modules/media/__init__.py` - Media processing helpers.
- `app/modules/media/processing.py` - FFmpeg/speech helpers for media processing.

#### app/modules/messaging/
- `app/modules/messaging/__init__.py` - Messaging domain exports.
- `app/modules/messaging/models.py` - SQLAlchemy models and enums for the messaging domain.
- `app/modules/messaging/schemas.py` - Messaging domain Pydantic schemas.

#### app/modules/moderation/
- `app/modules/moderation/__init__.py` - Moderation domain exports.
- `app/modules/moderation/models.py` - Moderation domain enums and models (blocks, bans, and related logs).
- `app/modules/moderation/schemas.py` - Pydantic schemas for the moderation domain (blocks, bans, reports).
- `app/modules/moderation/service.py` - Business logic for moderation workflows (warnings, bans, report handling).

#### app/modules/notifications/
- `app/modules/notifications/__init__.py` - Notifications domain package.
- `app/modules/notifications/analytics.py` - Analytics utilities for notifications.
- `app/modules/notifications/batching.py` - Batch processing helpers for notifications.
- `app/modules/notifications/common.py` - Shared helpers and state for the notifications domain.
- `app/modules/notifications/email.py` - Email delivery utilities for notifications.
- `app/modules/notifications/models.py` - SQLAlchemy models and enums for the notifications domain.
- `app/modules/notifications/realtime.py` - WebSocket connection management for real-time notifications.
- `app/modules/notifications/repository.py` - Data-access helpers for notifications domain.
- `app/modules/notifications/schemas.py` - Pydantic schemas dedicated to the notifications domain.
- `app/modules/notifications/service.py` - Core notification services, delivery management, and handlers.
- `app/modules/notifications/tasks.py` - Reusable task helpers for the notifications domain.

#### app/modules/posts/
- `app/modules/posts/__init__.py` - Posts domain public exports.
- `app/modules/posts/models.py` - Post domain SQLAlchemy models and enums.
- `app/modules/posts/schemas.py` - Pydantic schemas for posts reactions and vote analytics.
- `app/modules/posts/service.py` - Posts service exports.

#### app/modules/search/
- `app/modules/search/__init__.py` - Search domain package with schemas and stats update helpers.
- `app/modules/search/cache.py` - Utility helpers for caching search statistics/suggestions in Redis.
- `app/modules/search/schemas.py` - Pydantic schemas for search and search statistics.
- `app/modules/search/service.py` - Search domain services reused across routers and background jobs.
- `app/modules/search/typesense_client.py` - Minimal Typesense client wrapper for search offload; cached when enabled.

#### app/modules/social/
- `app/modules/social/__init__.py` - Social interactions package exports.
- `app/modules/social/economy_accel.py` - Thin Python wrapper for the Rust-accelerated social economy routines.
- `app/modules/social/economy_service.py` - social module utilities.
- `app/modules/social/models.py` - Social/interactions domain models.
- `app/modules/social/service.py` - Social service exports for backwards compatibility.

#### app/modules/stickers/
- `app/modules/stickers/__init__.py` - Sticker domain exports.
- `app/modules/stickers/models.py` - Sticker domain models and association tables.
- `app/modules/stickers/schemas.py` - Pydantic schemas for the stickers domain.

#### app/modules/support/
- `app/modules/support/__init__.py` - Support domain exports.
- `app/modules/support/models.py` - Support/helpdesk models and enums.
- `app/modules/support/schemas.py` - Pydantic schemas for support tickets.

#### app/modules/users/
- `app/modules/users/__init__.py` - User domain package exports.
- `app/modules/users/associations.py` - Association tables shared across user-related models.
- `app/modules/users/models.py` - SQLAlchemy models and enums for the users domain.
- `app/modules/users/schemas.py` - Pydantic schemas for the users domain.
- `app/modules/users/service.py` - Compatibility shim that re-exports the canonical user service.

#### app/modules/utils/
- `app/modules/utils/__init__.py` - Utility submodule exports for backward compatibility.
- `app/modules/utils/analytics.py` - Analytics and scoring utilities.
- `app/modules/utils/common.py` - Common helpers shared across utility modules.
- `app/modules/utils/content.py` - Content moderation, sentiment, and repost helpers.
- `app/modules/utils/events.py` - Event logging helpers.
- `app/modules/utils/files.py` - File and media utility helpers.
- `app/modules/utils/links.py` - Link preview helpers.
- `app/modules/utils/moderation.py` - Moderation-specific utility helpers.
- `app/modules/utils/network.py` - Networking helpers (IP management).
- `app/modules/utils/search.py` - Search utilities including spell checking.
- `app/modules/utils/security.py` - Security and authentication utilities.
- `app/modules/utils/translation.py` - Translation helpers with caching.

#### app/modules/wellness/
- `app/modules/wellness/__init__.py` - wellness package exports.
- `app/modules/wellness/models.py` - wellness domain models.
- `app/modules/wellness/service.py` - wellness domain services.

### app/routers/
- `app/routers/admin_dashboard.py` - Admin dashboard router exposing cached analytics and management endpoints.
- `app/routers/amenhotep.py` - Amenhotep AI router for chatbot interactions and analytics hooks.
- `app/routers/auth.py` - Authentication router with login/registration flows, 2FA, and rate-limit guards.
- `app/routers/banned_words.py` - Banned words router for managing moderation wordlists with severity levels.
- `app/routers/block.py` - Block/ban router handling user blocks, appeals, and admin enforcement.
- `app/routers/business.py` - Business router for business account verification and transactions.
- `app/routers/call.py` - Call router for audio/video call setup, updates, and screen-share integration.
- `app/routers/call_signaling.py` - WebSocket signaling for call rooms with authenticated handshakes and room security.
- `app/routers/category_management.py` - Category management router for CRUD on community/post categories.
- `app/routers/collaboration.py` - Collaboration router for projects and contributions management.
- `app/routers/comment.py` - Comment router handling CRUD, moderation flags, and legacy compatibility helpers.
- `app/routers/community.py` - Community router for membership, rules, invitations, and analytics endpoints.
- `app/routers/fact_checking.py` - Fact checking router for submitting facts, verifications, corrections, and badges.
- `app/routers/follow.py` - Follow router for follow/unfollow flows and follower listings.
- `app/routers/hashtag.py` - Hashtag router for CRUD, analytics, and popularity calculations.
- `app/routers/impact.py` - Impact router for issuing impact certificates and managing cultural dictionary entries.
- `app/routers/message.py` - Message router for direct/group messaging including media and legacy shims.
- `app/routers/moderation.py` - Moderation router for warnings, bans, IP bans, and block appeals.
- `app/routers/moderator.py` - Moderator router for handling reports review and block appeals.
- `app/routers/notifications.py` - Notifications router covering preferences, feeds, and delivery/analytics operations.
- `app/routers/oauth.py` - OAuth router handling Google OAuth flows and token exchange callbacks.
- `app/routers/p2fa.py` - Two-factor auth router (OTP setup/verification) for account security.
- `app/routers/post.py` - Posts router.
- `app/routers/reaction.py` - Reaction router for post/comment reactions and trending calculations.
- `app/routers/reels.py` - Router for managing reels lifecycle and cleanup endpoints.
- `app/routers/report.py` - Reporting router for abuse reports on posts/comments.
- `app/routers/screen_share.py` - Screen share router handling start/stop/update lifecycle and notifications.
- `app/routers/search.py` - Search router covering plain and advanced search with spell suggestions and cache integration.
- `app/routers/session.py` - Session router for managing encrypted session setup, key updates, and teardown.
- `app/routers/social_auth.py` - Social auth router for Facebook/Twitter OAuth flows.
- `app/routers/statistics.py` - Statistics router for system/community analytics and user activity aggregates.
- `app/routers/sticker.py` - Sticker router for packs/categories/reports and media upload validation.
- `app/routers/support.py` - Support router for ticket creation, responses, and status updates.
- `app/routers/user.py` - User router covering profile, preferences, followers, language, and session endpoints.
- `app/routers/vote.py` - Vote router for post voting and side-effect hooks.
- `app/routers/wellness.py` - Wellness router for metrics, alerts, sessions, modes, and goals.

### app/services/
- `app/services/business/__init__.py` - Business domain services.
- `app/services/business/service.py` - Business account services for verification and transaction handling.
- `app/services/comments/__init__.py` - Comment domain services.
- `app/services/comments/service.py` - Service layer handling comment operations with scoring, moderation, translation, and notification side effects.
- `app/services/community/__init__.py` - Community domain services.
- `app/services/community/service.py` - Community domain business logic for memberships, rules, invitations, and content stats.
- `app/services/local_economy_service.py` - Lightweight service helpers for local economy flows (marketplace/learning).
- `app/services/messaging/__init__.py` - Messaging domain services.
- `app/services/messaging/call_service.py` - Service layer for call management: setup, status transitions, and quality safeguards.
- `app/services/messaging/message_service.py` - Service layer encapsulating messaging workflows with legacy shims and media handling.
- `app/services/moderation/__init__.py` - Moderation services.
- `app/services/moderation/banned_word_service.py` - Service layer for managing banned words.
- `app/services/posts/__init__.py` - Posts service exports.
- `app/services/posts/post_service.py` - Service layer for post operations with content safety, scheduling, notifications, and legacy shims.
- `app/services/posts/vote_service.py` - Business logic for voting and reactions on posts.
- `app/services/reels/__init__.py` - Service layer for __init__.
- `app/services/reels/service.py` - Reel service for lifecycle management, cleanup, and engagement metrics.
- `app/services/reporting.py` - Reporting utilities for abuse reports and auto-expiry of ban statistics.
- `app/services/social/__init__.py` - Social domain service exports.
- `app/services/social/follow_service.py` - Business logic for follow/unfollow flows and follower analytics.
- `app/services/support_service.py` - Support ticket ancillary flows for creation, responses, and moderation.
- `app/services/users/__init__.py` - Users service package.
- `app/services/users/service.py` - High-level business services for the users domain.

## scripts/
- `scripts/check_migrations.py` - CI helper to validate Alembic migrations on a clean SQLite database.
- `scripts/check_subclass.py` - Script: check_subclass.
- `scripts/db_backup.py` - Postgres backup helper using pg_dump.
- `scripts/export_amenhotep_onnx.py` - Utility to export the Amenhotep (bert-base-arabertv02) model to ONNX for faster inference.
- `scripts/locustfile.py` - Basic Locust load test hitting health and a sample API route.
- `scripts/perf_api_latency.py` - Lightweight API latency benchmark (in-process ASGI).
- `scripts/perf_startup.py` - Lightweight startup benchmark for the FastAPI application.

## tests/
- `tests/__init__.py` - Test coverage for __init__.
- `tests/conftest.py` - Test coverage for conftest.
- `tests/database.py` - Test coverage for database.
- `tests/testclient.py` - Test coverage for testclient.
- `tests/admin/test_admin_dashboard.py` - Test coverage for test_admin_dashboard.
- `tests/admin/test_admin_dashboard_coverage.py` - Test coverage for test_admin_dashboard_coverage.
- `tests/admin/test_auth_oauth_admin.py` - Test coverage for test_auth_oauth_admin.
- `tests/admin/test_notifications_admin.py` - Test coverage for test_notifications_admin.
- `tests/admin/test_phase8_admin_moderation.py` - Test coverage for test_phase8_admin_moderation.
- `tests/ai/test_ai_amenhotep_and_edit_history.py` - Test coverage for test_ai_amenhotep_and_edit_history.
- `tests/ai/test_amenhotep_cache_and_init.py` - Test coverage for test_amenhotep_cache_and_init.
- `tests/ai/test_amenhotep_content_i18n.py` - Test coverage for test_amenhotep_content_i18n.
- `tests/ai/test_amenhotep_coverage.py` - Test coverage for test_amenhotep_coverage.
- `tests/ai/test_amenhotep_onnx_and_session.py` - Test coverage for test_amenhotep_onnx_and_session.
- `tests/ai/test_amenhotep_onnx_cache.py` - Test coverage for test_amenhotep_onnx_cache.
- `tests/ai/test_amenhotep_router_ws_coverage.py` - Test coverage for test_amenhotep_router_ws_coverage.
- `tests/ai/test_notifications_email_batch.py` - Test coverage for test_notifications_email_batch.
- `tests/ai/test_utils_links_search_amenhotep_gaps.py` - Test coverage for test_utils_links_search_amenhotep_gaps.
- `tests/analytics/test_analytics_charts_coverage.py` - Test coverage for test_analytics_charts_coverage.
- `tests/analytics/test_analytics_core.py` - Test coverage for test_analytics_core.
- `tests/analytics/test_analytics_lazy.py` - Test coverage for test_analytics_lazy.
- `tests/analytics/test_analytics_logging.py` - Test coverage for test_analytics_logging.
- `tests/analytics/test_analytics_metrics.py` - Test coverage for test_analytics_metrics.
- `tests/analytics/test_analytics_queries.py` - Test coverage for test_analytics_queries.
- `tests/analytics/test_impact_api.py` - Test coverage for test_impact_api.
- `tests/analytics/test_notifications_celery_process_and_analytics.py` - Test coverage for test_notifications_celery_process_and_analytics.
- `tests/analytics/test_utils_content_analytics.py` - Test coverage for test_utils_content_analytics.
- `tests/auth/test_auth_coverage.py` - Test coverage for test_auth_coverage.
- `tests/auth/test_auth_login_refresh.py` - Test coverage for test_auth_login_refresh.
- `tests/auth/test_auth_p2fa_middleware.py` - Test coverage for test_auth_p2fa_middleware.
- `tests/auth/test_auth_router.py` - Test coverage for test_auth_router.
- `tests/auth/test_auth_security_extended.py` - Test coverage for test_auth_security_extended.
- `tests/auth/test_auth_tokens_and_login.py` - Test coverage for test_auth_tokens_and_login.
- `tests/auth/test_crypto_oauth2.py` - Test coverage for test_crypto_oauth2.
- `tests/auth/test_crypto_oauth2_more_coverage.py` - Test coverage for test_crypto_oauth2_more_coverage.
- `tests/auth/test_oauth_router_more_coverage.py` - Test coverage for test_oauth_router_more_coverage.
- `tests/auth/test_oauth_social.py` - Test coverage for test_oauth_social.
- `tests/auth/test_p2fa_router_more_coverage.py` - Test coverage for test_p2fa_router_more_coverage.
- `tests/auth/test_social_auth_more_coverage.py` - Test coverage for test_social_auth_more_coverage.
- `tests/auth/test_websocket_auth.py` - Test coverage for test_websocket_auth.
- `tests/comments/test_comment_service_basic.py` - Test coverage for test_comment_service_basic.
- `tests/comments/test_comment_service_extended.py` - Test coverage for test_comment_service_extended.
- `tests/community/test_collaboration_and_memory.py` - Test coverage for test_collaboration_and_memory.
- `tests/community/test_collaboration_api.py` - Test coverage for test_collaboration_api.
- `tests/community/test_collaboration_router_more_coverage.py` - Test coverage for test_collaboration_router_more_coverage.
- `tests/community/test_community.py` - Test coverage for test_community.
- `tests/community/test_community_posts.py` - Test coverage for test_community_posts.
- `tests/community/test_community_router_basic.py` - Test coverage for test_community_router_basic.
- `tests/community/test_community_router_membership.py` - Test coverage for test_community_router_membership.
- `tests/community/test_community_service_basic.py` - Test coverage for test_community_service_basic.
- `tests/community/test_community_service_core.py` - Test coverage for test_community_service_core.
- `tests/community/test_community_service_extra.py` - Test coverage for test_community_service_extra.
- `tests/community/test_community_service_limits.py` - Test coverage for test_community_service_limits.
- `tests/community/test_community_service_roles_stats.py` - Test coverage for test_community_service_roles_stats.
- `tests/community/test_community_stats.py` - Test coverage for test_community_stats.
- `tests/content/test_category_management_coverage.py` - Test coverage for test_category_management_coverage.
- `tests/content/test_content_reels_articles.py` - Test coverage for test_content_reels_articles.
- `tests/content/test_content_routers.py` - Test coverage for test_content_routers.
- `tests/content/test_file_management.py` - Test coverage for test_file_management.
- `tests/content/test_hashtag_router_coverage.py` - Test coverage for test_hashtag_router_coverage.
- `tests/content/test_living_memory.py` - Test coverage for test_living_memory.
- `tests/content/test_media.py` - Test coverage for test_media.
- `tests/content/test_media_uploads.py` - Test coverage for test_media_uploads.
- `tests/content/test_media_utils.py` - Test coverage for test_media_utils.
- `tests/content/test_post_edge_cases.py` - Test coverage for test_post_edge_cases.
- `tests/content/test_post_flags.py` - Test coverage for test_post_flags.
- `tests/content/test_post_service_additional.py` - Test coverage for test_post_service_additional.
- `tests/content/test_post_service_create_and_notifications.py` - Test coverage for test_post_service_create_and_notifications.
- `tests/content/test_post_service_extra.py` - Test coverage for test_post_service_extra.
- `tests/content/test_post_service_polls_and_memory.py` - Test coverage for test_post_service_polls_and_memory.
- `tests/content/test_post_service_reposts_and_translation.py` - Test coverage for test_post_service_reposts_and_translation.
- `tests/content/test_post_service_rules_and_scheduling.py` - Test coverage for test_post_service_rules_and_scheduling.
- `tests/content/test_post_translation_flag.py` - Test coverage for test_post_translation_flag.
- `tests/content/test_posts.py` - Test coverage for test_posts.
- `tests/content/test_posts_router.py` - Test coverage for test_posts_router.
- `tests/content/test_reaction_router_coverage.py` - Test coverage for test_reaction_router_coverage.
- `tests/content/test_reels.py` - Test coverage for test_reels.
- `tests/content/test_social_media_accounts.py` - Test coverage for test_social_media_accounts.
- `tests/content/test_sticker_router.py` - Test coverage for test_sticker_router.
- `tests/content/test_utils_content.py` - Test coverage for test_utils_content.
- `tests/content/test_utils_content_gaps.py` - Test coverage for test_utils_content_gaps.
- `tests/content/test_vote_router_more_coverage.py` - Test coverage for test_vote_router_more_coverage.
- `tests/content/test_vote_service.py` - Test coverage for test_vote_service.
- `tests/content/test_votes.py` - Test coverage for test_votes.
- `tests/core/test_app_factory_errors.py` - Test coverage for test_app_factory_errors.
- `tests/core/test_app_factory_health_and_https.py` - Test coverage for test_app_factory_health_and_https.
- `tests/core/test_app_factory_https_trustedhost.py` - Test coverage for test_app_factory_https_trustedhost.
- `tests/core/test_app_factory_more_coverage.py` - Test coverage for test_app_factory_more_coverage.
- `tests/core/test_app_factory_routes.py` - Test coverage for test_app_factory_routes.
- `tests/core/test_app_factory_static_and_ready.py` - Test coverage for test_app_factory_static_and_ready.
- `tests/core/test_cache.py` - Test coverage for test_cache.
- `tests/core/test_cache_and_db_helpers.py` - Test coverage for test_cache_and_db_helpers.
- `tests/core/test_cache_and_scheduling.py` - Test coverage for test_cache_and_scheduling.
- `tests/core/test_celery.py` - Test coverage for test_celery.
- `tests/core/test_celery_worker_coverage.py` - Test coverage for test_celery_worker_coverage.
- `tests/core/test_celery_worker_more_coverage.py` - Test coverage for test_celery_worker_more_coverage.
- `tests/core/test_core_config_cache.py` - Test coverage for test_core_config_cache.
- `tests/core/test_core_database_helpers_coverage.py` - Test coverage for test_core_database_helpers_coverage.
- `tests/core/test_core_exceptions_coverage.py` - Test coverage for test_core_exceptions_coverage.
- `tests/core/test_core_infrastructure.py` - Test coverage for test_core_infrastructure.
- `tests/core/test_core_scheduling_tasks.py` - Covers scheduler startup/beat wiring and environment guards without touching real schedulers or Firebase.
- `tests/core/test_database_engine.py` - Test coverage for test_database_engine.
- `tests/core/test_database_fixture_and_helpers.py` - Test coverage for test_database_fixture_and_helpers.
- `tests/core/test_db_app_factory.py` - Test coverage for test_db_app_factory.
- `tests/core/test_https_hosts_rate_limit.py` - Test coverage for test_https_hosts_rate_limit.
- `tests/core/test_logging_and_middleware.py` - Test coverage for test_logging_and_middleware.
- `tests/core/test_logging_middleware.py` - Test coverage for test_logging_middleware.
- `tests/core/test_middleware_and_settings.py` - Test coverage for test_middleware_and_settings.
- `tests/core/test_monitoring_and_redis_cache.py` - Test coverage for test_monitoring_and_redis_cache.
- `tests/core/test_monitoring_telemetry_coverage.py` - Test coverage for test_monitoring_telemetry_coverage.
- `tests/core/test_query_helpers.py` - Test coverage for test_query_helpers.
- `tests/core/test_redis_cache.py` - Test coverage for test_redis_cache.
- `tests/core/test_redis_cache_more_coverage.py` - Test coverage for test_redis_cache_more_coverage.
- `tests/core/test_scheduling.py` - Test coverage for test_scheduling.
- `tests/core/test_scheduling_tasks_core.py` - Test coverage for test_scheduling_tasks_core.
- `tests/core/test_scheduling_tasks_jobs.py` - Test coverage for test_scheduling_tasks_jobs.
- `tests/core/test_settings.py` - Test coverage for test_settings.
- `tests/core/test_settings_more_coverage.py` - Test coverage for test_settings_more_coverage.
- `tests/core/test_shims_exports.py` - Test coverage for test_shims_exports.
- `tests/core/test_telemetry.py` - Test coverage for test_telemetry.
- `tests/core/test_telemetry_logging.py` - Test coverage for test_telemetry_logging.
- `tests/e2e/test_e2e_lifecycle.py` - Test coverage for test_e2e_lifecycle.
- `tests/e2e/test_end_to_end.py` - Test coverage for test_end_to_end.
- `tests/economy/test_business_router_coverage.py` - Test coverage for test_business_router_coverage.
- `tests/economy/test_economy_accel_coverage.py` - Test coverage for test_economy_accel_coverage.
- `tests/economy/test_local_economy_models.py` - Test coverage for test_local_economy_models.
- `tests/economy/test_local_economy_service.py` - Test coverage for test_local_economy_service.
- `tests/economy/test_local_economy_service_more_coverage.py` - Test coverage for test_local_economy_service_more_coverage.
- `tests/economy/test_local_economy_support_reporting.py` - Test coverage for test_local_economy_support_reporting.
- `tests/economy/test_social_economy_interactions.py` - Test coverage for test_social_economy_interactions.
- `tests/economy/test_social_economy_models.py` - Test coverage for test_social_economy_models.
- `tests/economy/test_social_economy_service.py` - Test coverage for test_social_economy_service.
- `tests/flows/__init__.py` - Test coverage for __init__.
- `tests/flows/test_misc_flows.py` - Test coverage for test_misc_flows.
- `tests/flows/test_negative_paths.py` - Test coverage for test_negative_paths.
- `tests/flows/test_resilience.py` - Test coverage for test_resilience.
- `tests/flows/test_router_mixed_flows.py` - Test coverage for test_router_mixed_flows.
- `tests/flows/test_router_smoke_suite.py` - Test coverage for test_router_smoke_suite.
- `tests/flows/test_search_and_notifications_flow.py` - Test coverage for test_search_and_notifications_flow.
- `tests/flows/test_services_misc.py` - Test coverage for test_services_misc.
- `tests/flows/test_services_mixed.py` - Test coverage for test_services_mixed.
- `tests/integrations/test_firebase_config.py` - Test coverage for test_firebase_config.
- `tests/messaging/test_call_and_screen_share.py` - Test coverage for test_call_and_screen_share.
- `tests/messaging/test_call_router_more_coverage.py` - Test coverage for test_call_router_more_coverage.
- `tests/messaging/test_call_service.py` - Test coverage for test_call_service.
- `tests/messaging/test_call_signaling.py` - Test coverage for test_call_signaling.
- `tests/messaging/test_calls_and_screen_share.py` - Test coverage for test_calls_and_screen_share.
- `tests/messaging/test_group_messaging.py` - Test coverage for test_group_messaging.
- `tests/messaging/test_message.py` - Test coverage for test_message.
- `tests/messaging/test_message_service_attachments_and_limits.py` - Test coverage for test_message_service_attachments_and_limits.
- `tests/messaging/test_message_service_core.py` - Test coverage for test_message_service_core.
- `tests/messaging/test_messaging_moderation.py` - Integration-style test for messaging service flows with moderation hooks and notification stubs.
- `tests/messaging/test_messaging_router.py` - Test coverage for test_messaging_router.
- `tests/messaging/test_realtime_and_moderation.py` - Test coverage for test_realtime_and_moderation.
- `tests/moderation/test_banned_words_router.py` - Test coverage for test_banned_words_router.
- `tests/moderation/test_block_and_moderation.py` - Test coverage for test_block_and_moderation.
- `tests/moderation/test_block_moderation.py` - Test coverage for test_block_moderation.
- `tests/moderation/test_moderation_blocks.py` - Test coverage for test_moderation_blocks.
- `tests/moderation/test_moderation_coverage.py` - Test coverage for test_moderation_coverage.
- `tests/moderation/test_moderation_wellness_reels.py` - Test coverage for test_moderation_wellness_reels.
- `tests/moderation/test_moderator_router_coverage.py` - Test coverage for test_moderator_router_coverage.
- `tests/notifications/test_notifications.py` - Test coverage for test_notifications.
- `tests/notifications/test_notifications_batcher_coverage.py` - Test coverage for test_notifications_batcher_coverage.
- `tests/notifications/test_notifications_batching_and_caches.py` - Test coverage for test_notifications_batching_and_caches.
- `tests/notifications/test_notifications_batching_more_coverage.py` - Test coverage for test_notifications_batching_more_coverage.
- `tests/notifications/test_notifications_celery_and_push.py` - Test coverage for test_notifications_celery_and_push.
- `tests/notifications/test_notifications_delivery_manager.py` - Test coverage for test_notifications_delivery_manager.
- `tests/notifications/test_notifications_extra.py` - Test coverage for test_notifications_extra.
- `tests/notifications/test_notifications_repository_and_common.py` - Test coverage for test_notifications_repository_and_common.
- `tests/notifications/test_notifications_retry_handler.py` - Test coverage for test_notifications_retry_handler.
- `tests/notifications/test_notifications_router.py` - Test coverage for test_notifications_router.
- `tests/notifications/test_notifications_router_more_coverage.py` - Test coverage for test_notifications_router_more_coverage.
- `tests/notifications/test_notifications_scheduling.py` - Test coverage for test_notifications_scheduling.
- `tests/notifications/test_notifications_service_basics.py` - Test coverage for test_notifications_service_basics.
- `tests/notifications/test_notifications_service_channels_cache.py` - Test coverage for test_notifications_service_channels_cache.
- `tests/notifications/test_notifications_service_core.py` - Test coverage for test_notifications_service_core.
- `tests/notifications/test_notifications_service_coverage.py` - Test coverage for test_notifications_service_coverage.
- `tests/notifications/test_notifications_service_more_coverage.py` - Test coverage for test_notifications_service_more_coverage.
- `tests/notifications/test_notifications_service_retries_and_errors.py` - Test coverage for test_notifications_service_retries_and_errors.
- `tests/notifications/test_notifications_tasks.py` - Test coverage for test_notifications_tasks.
- `tests/notifications/test_notifications_tasks_and_ws.py` - Test coverage for test_notifications_tasks_and_ws.
- `tests/notifications/test_notifications_tasks_jobs.py` - Test coverage for test_notifications_tasks_jobs.
- `tests/notifications/test_ws_notifications.py` - Test coverage for test_ws_notifications.
- `tests/search/test_search_cache_core.py` - Test coverage for test_search_cache_core.
- `tests/search/test_search_cache_layer.py` - Test coverage for test_search_cache_layer.
- `tests/search/test_search_cache_queries.py` - Test coverage for test_search_cache_queries.
- `tests/search/test_search_cache_typesense.py` - Covers search cache (Redis-like) helpers and Typesense client fallback without real network/Redis.
- `tests/search/test_search_router_core.py` - Test coverage for test_search_router_core.
- `tests/search/test_search_router_fallbacks.py` - Test coverage for test_search_router_fallbacks.
- `tests/search/test_search_typesense.py` - Test coverage for test_search_typesense.
- `tests/search/test_typesense_integration.py` - Test coverage for test_typesense_integration.
- `tests/security/test_security_permissions.py` - Test coverage for test_security_permissions.
- `tests/security/test_security_sessions.py` - Test coverage for test_security_sessions.
- `tests/security/test_security_settings.py` - Test coverage for test_security_settings.
- `tests/support/test_fact_and_wellness.py` - Test coverage for test_fact_and_wellness.
- `tests/support/test_fact_checking_and_support.py` - Test coverage for test_fact_checking_and_support.
- `tests/support/test_fact_checking_service.py` - Test coverage for test_fact_checking_service.
- `tests/support/test_reporting.py` - Test coverage for test_reporting.
- `tests/support/test_services_enforcement_and_reporting.py` - Test coverage for test_services_enforcement_and_reporting.
- `tests/support/test_support_reporting.py` - Test coverage for test_support_reporting.
- `tests/support/test_support_status_routes.py` - Test coverage for test_support_status_routes.
- `tests/support/test_wellness_service.py` - Test coverage for test_wellness_service.
- `tests/users/test_follow_api.py` - Test coverage for test_follow_api.
- `tests/users/test_privacy_features.py` - Test coverage for test_privacy_features.
- `tests/users/test_user_identities.py` - Test coverage for test_user_identities.
- `tests/users/test_user_service_core.py` - Test coverage for test_user_service_core.
- `tests/users/test_user_service_profiles_followers.py` - Test coverage for test_user_service_profiles_followers.
- `tests/users/test_user_service_security.py` - Test coverage for test_user_service_security.
- `tests/users/test_users.py` - Test coverage for test_users.
- `tests/users/test_users_comments_sessions.py` - Test coverage for test_users_comments_sessions.
- `tests/utils/test_link_preview.py` - Test coverage for test_link_preview.
- `tests/utils/test_utils.py` - Test coverage for test_utils.
- `tests/utils/test_utils_extended.py` - Test coverage for test_utils_extended.
- `tests/utils/test_utils_network_additional.py` - Test coverage for test_utils_network_additional.
- `tests/utils/test_utils_network_core.py` - Test coverage for test_utils_network_core.
- `tests/utils/test_utils_network_gaps.py` - Test coverage for test_utils_network_gaps.
- `tests/utils/test_utils_search_core.py` - Test coverage for test_utils_search_core.
- `tests/utils/test_utils_search_extra.py` - Test coverage for test_utils_search_extra.
## go/
- `go/realtime/main.go` - Redis-backed WebSocket fanout gateway.
- `go/realtime/go.mod` - Go module metadata for the realtime gateway.
- `go/realtime/README.md` - Setup and runtime notes for the gateway.

## rust/
- `rust/social_economy/src/lib.rs` - PyO3 scoring helpers for social economy metrics.
- `rust/social_economy/Cargo.toml` - Crate metadata and dependency list.
- `rust/social_economy/Cargo.lock` - Locked dependency graph for reproducible builds.
- `rust/social_economy/README.md` - Build and integration notes for the crate.

## Ops and config
- `Dockerfile`
- `docker-compose.yml`
- `docker-compose-dev.yml`
- `docker-compose-prod.yml`
- `docker-compose.monitoring.yml`
- `alembic.ini`
- `requirements.txt`
- `pyproject.toml`
- `Procfile`

## k8s/
- `k8s/api-configmap.yaml`
- `k8s/api-deployment.yaml`
- `k8s/api-hpa.yaml`
- `k8s/api-secrets.yaml`
- `k8s/api-service.yaml`
- `k8s/kustomization.yaml`
- `k8s/postgres-service.yaml`
- `k8s/postgres-statefulset.yaml`
- `k8s/redis-deployment.yaml`
- `k8s/redis-service.yaml`
- `k8s/rsa-keys-secret.yaml`

## monitoring/
- `monitoring/grafana/dashboards/fastapi.json`
- `monitoring/grafana/provisioning/dashboards/dashboard.yml`
- `monitoring/grafana/provisioning/datasources/datasource.yml`
- `monitoring/prometheus.yml`

## docs/
- `docs/API_REFERENCE.md`
- `docs/DATA_MODEL.md`
- `docs/FEATURE_FLOWS.md`
- `docs/PROJECT_REFERENCE.md`
- `docs/REPO_REFERENCE.md`
- `docs/SCALABILITY.md`
- `docs/TESTS_REFERENCE.md`

## data/
- `data/amenhotep/knowledge_base.json`

## static/
- `static/doc.pdf`
- `static/media/clip.mp4`
- `static/media/doc.pdf`
- `static/messages/a.txt`
- `static/messages/empty_file.txt`
- `static/messages/test.txt`
- `static/messages/test_file.txt`
- `static/profile_images/1_p.png`
- `static/terms_of_service.md`
- `static/test.pdf`

