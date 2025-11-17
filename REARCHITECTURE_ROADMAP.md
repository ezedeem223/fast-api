# Re-Architecture Roadmap (v2)

This revision replaces the previous roadmap with a concise, three-part plan that addresses the remaining structural gaps and sets up the project for long-term maintainability. Each part contains concrete objectives that map directly to the issues identified during the recent audit.

---

## Part 1 – Domain Isolation & Schema Hygiene
1. **Split monolithic schemas**  
   - Extract user/post/community/notification/search schemas into `app/modules/<domain>/schemas.py`.  
   - Keep `app/schemas.py` as a lightweight compatibility aggregator that re-exports the modular schemas during the transition.
2. **Finalize notifications/domain modules**  
   - Move `ConnectionManager`, email helpers, and queue utilities from `app/notifications.py` into `app/modules/notifications/` and adjust router/service imports accordingly.  
   - Remove any dead code left in the legacy module once consumers migrate.
3. **Modularize moderation/media helpers**  
   - Relocate `app/moderation.py` and `app/media_processing.py` logic into dedicated module/service packages so routers remain thin and consistent with other domains.

## Part 2 – Core Platform Hardening
1. **Unify configuration & database layers**  
   - Deprecate legacy `app/config.py` and `app/database.py` in favor of `app/core/config/settings.py` and `app/core/database/session.py`.  
   - Provide clear migration guidance (or shims) to prevent ambiguous imports.
2. **Slim the FastAPI entrypoint**  
   - Extract WebSocket management, exception handlers, and middleware wiring from `app/main.py` into `app/core/middleware`/`app/integrations`.  
   - Ensure the main module handles only app creation plus router inclusion.
3. **Lazy-load heavy analytics dependencies**  
   - Wrap transformer initialization in `app/analytics.py` so models load on demand (or via dependency injection) to keep startup/testing fast.  
   - Confirm background tasks (search/vector updates, Firebase init) gracefully degrade in test environments.

## Part 3 – Quality Gates & Operational Confidence
1. **Targeted test coverage**  
   - Add unit tests for the new modular schemas, utility helpers (search ordering, analytics lazy-loading), and scheduling middleware.  
   - Ensure pytest continues to run in strict asyncio mode without warnings.
2. **Performance & startup checks**  
   - Introduce lightweight benchmarks or profiling scripts to detect regressions from background jobs or AI model loading.  
   - Include CI hooks (e.g., GitHub Actions) to run these checks on pull requests.
3. **Documentation & handover**  
   - Update developer docs to describe the final module layout, dependency injection expectations, and common extension points.  
   - Provide a brief migration guide for teams adding new routers/services so they follow the modular patterns by default.

---

**Execution guidance:**  
Tackle the parts sequentially but keep changes reviewable by shipping each bullet as an independent PR/commit. After each part, rerun `python -m pytest -q` and perform a manual smoke test (auth, posts, messaging) to confirm functional parity.
