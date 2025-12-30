# Coverage Expansion Plan (30 Sessions, 3 Points × 3 Tests Each)

Each session targets low-coverage/high-risk areas. Every point lists three concrete test scenarios (total 9 per session). No duplicates across points.

1. Session 1 — `app/ai_chat/amenhotep.py`
   - ONNX path: present loads; missing falls back; corrupt file raises and falls back.
   - Session context trimming: >10 exchanges keeps last 10; reset path; retrieval after trim.
   - Knowledge base hit/miss: topic match returns content; miss uses model; model generation exception handled.

2. Session 2 — `app/ai_chat/amenhotep.py`
   - Embedding cache TTL/eviction: hit before TTL; expires after TTL; max-size eviction drops oldest.
   - PyTorch init paths: GPU available; CPU fallback; model load failure handled.
   - Response formatting: Arabic input preserved; English capitalized; symbols unchanged.

3. Session 3 — `app/analytics.py`
   - `merge_stats`: numeric sum; type conflict keeps incoming; None inputs return merged defaults.
   - Sentiment pipeline: model available; model load failure handled; empty text short-circuit.
   - `suggest_improvements`: negative/high score triggers advice; short text advice; neutral message.

4. Session 4 — `app/analytics.py`
   - `log_analysis_event`: success log; failure log with exception; missing context handled.
   - `get_user_activity`: no events; mixed event types aggregated; custom days window.
   - `get_problematic_users`: threshold 0 returns all; threshold 5 filters; >30 days excluded.

5. Session 5 — `app/api/websocket.py`
   - Auth missing token: prod rejects 4401; test allows; PYTEST_CURRENT_TEST override in prod except specific test.
   - Token validation: invalid token closes 4401; user mismatch closes 1008; valid token passes.
   - Disconnect handling: empty message triggers disconnect; WebSocketDisconnect cleans up; exception path closes 1011.

6. Session 6 — `app/celery_worker.py`
   - Test mode eager: memory broker/backend set; beat schedule cleared; task executes inline.
   - `cleanup_old_notifications`: success commits; task exception rolls back; session always closed.
   - `process_scheduled_notifications`: enqueues on pending; marks delivered; handles empty queue gracefully.

7. Session 7 — `app/core/app_factory.py`
   - HTTPS/hosts: TrustedHost applied when list set; force_https redirect in prod; disabled in test.
   - Readiness check: DB ping success; DB failure returns 503; Redis configured without client marks not ready.
   - Content classifier training: artifacts present skip training; missing files trigger train; test env skips training.

8. Session 8 — `app/core/cache/redis_cache.py`
   - Init cache: valid URL enables; invalid URL sets failed_init; missing URL leaves disabled.
   - set/get paths: normal Redis stores; fallback store used when client lacks get/set; TTL expiry removes entries.
   - Invalidation: scan finds keys deleted; no-match no error; Redis error logged without raise.

9. Session 9 — `app/core/config/settings.py`
   - Allowed hosts: JSON string; comma list; default adds testserver in test env.
   - force_https: production with unset enables; env false disables; env true enables.
   - `_read_key_file`: relative path resolves; absolute path read; empty file raises ValueError.

10. Session 10 — `app/core/database/__init__.py` & `session.py`
    - `build_engine`: postgres options applied; sqlite check_same_thread false; connect_args empty otherwise.
    - `get_db`: normal yield closes; exception closes; nested generator only one session.
    - Session configuration: SessionLocal binds engine; sessionmaker attributes (autocommit/autoflush) preserved; query_helpers import fallback.

11. Session 11 — `app/core/middleware/logging_middleware.py`
    - Logging contents: small body logged; large body truncated; exception path logged with status.
    - Ordering: middleware runs before CORS/language; request_id propagation present; next middleware receives same context.
    - Health path: `/livez` excluded from noisy logging; non-health included; header passthrough verified.

12. Session 12 — `app/core/telemetry.py`
    - OTEL disabled: enabled flag false skips instrumentation; missing package skips safely; console exporter used when no endpoint.
    - Instrumentors: Redis instrumentation failure logged but continues; Psycopg2 instrumented; Requests instrumented.
    - Sentry setup: DSN provided initializes; DSN missing no-op; sentry-sdk missing logs warning.

13. Session 13 — `app/modules/media/processing.py`
    - `extract_audio_from_video`: valid mp4 produces wav; missing file raises; ffmpeg error logged.
    - `speech_to_text`: UnknownValueError returns empty; RequestError logs and returns empty; successful transcription.
    - `scan_file_for_viruses`: result FOUND returns False; clean returns True; clamd exception logs and returns True.

14. Session 14 — `app/modules/utils/content.py`
    - NLP mode: USE_LIGHTWEIGHT_NLP stub returns defaults; real pipeline loads; load failure handled.
    - `check_content_against_rules`: regex rule matches; non-matching content passes; case-insensitive match.
    - `train_content_classifier`: creates artifacts; reuse existing files; IO failure raises.

15. Session 15 — `app/modules/utils/search.py` & cache
    - Cache keys: hit returns cached; miss stores; eviction when over limit.
    - Search vector update: handles non-Latin text; empty text; large list processed without crash.
    - Spell helper: suggestion for typo; no suggestion; resilient to missing dictionary.

16. Session 16 — `app/modules/utils/network.py`
    - `get_client_ip`: uses X-Forwarded-For first; falls back to client; empty headers safe default.
    - `is_ip_banned`: active ban blocks; expired ban cleared and allowed; ProgrammingError fails open.
    - `detect_ip_evasion`: differing private/public flags flagged; identical IPs not flagged; multiple historical IPs mix.

17. Session 17 — `app/modules/notifications/service.py`
    - Channel selection: no channels logs warning; email-only sends once; push+realtime both invoked.
    - Retry logic: increments retry_count and schedules until max; success before max clears error; at max triggers final failure handler.
    - Realtime broadcast: publishes when REALTIME_REDIS_URL set; bad URL safely ignored; redis module missing no-op.

18. Session 18 — `app/modules/notifications/email.py` & batching
    - Email send: attachment path valid; SMTP failure logged; language translation applied.
    - Batcher: flush by size threshold; flush by timeout; flush handles task exception without loss of remaining queue.
    - Priority cache: set/get hit; eviction on new priority replacing old; cache clear resets.

19. Session 19 — `app/services/messaging/message_service.py`
    - `send_file`: empty file returns 400; >10MB returns 413; unsupported extension rejected.
    - `_get_or_create_direct_conversation`: new conversation created; existing reused; concurrent call does not duplicate members.
    - `mark_message_as_read`: sends notification when allowed; when sender disallows skip; missing message 404.

20. Session 20 — `app/services/messaging/message_service.py`
    - `_save_message_attachments`: writes multiple files; enforces size limit; bad path raises handled.
    - `search_messages`: filters by date range; by type; invalid sort raises validation error.
    - `update_message`: edit window expired returns 403; non-sender 403; valid edit succeeds.

21. Session 21 — `app/services/posts/post_service.py`
    - `_create_pdf`: returns PDF stream; pisa failure returns None; empty content handled.
    - `create_post`: mention notification sent; offensive content blocked; scheduled publish enqueued.
    - Repost stats: update_repost_statistics called; Twitter share stub invoked; Facebook share stub invoked.

22. Session 22 — `app/services/posts/post_service.py`
    - Media download: file missing 404; unauthorized requester 403; owner retrieves 200.
    - Poll voting: second vote blocked; invalid option 404; valid vote increments counts.
    - Living testimony: metadata present returns first; absent returns None; multiple entries handled.

23. Session 23 — `app/services/users/service.py`
    - Register: duplicate email rejected; invalid format rejected; valid user created.
    - Login: IP banned returns 403; 2FA required missing code rejected; correct code succeeds.
    - Update profile: privacy_level public/private/custom; custom saves map; invalid value rejected.

24. Session 24 — `app/services/community/service.py`
    - Create community: exceeds ownership limit raises; duplicate name rejected; valid create persists.
    - Join community: valid invitation accepted; expired invitation rejected; banned user blocked.
    - Update rule: owner allowed; member forbidden; moderator allowed based on role flag.

25. Session 25 — `app/routers/auth.py` & OAuth
    - `/login`: missing fields 422; correct credentials 200; locked account 423.
    - `/refresh`: blacklisted token 401; valid token issues new; expired token 401.
    - OAuth flow: state mismatch 400; valid code exchanges token; provider error handled.

26. Session 26 — `app/routers/community.py`
    - Get community by id: member 200; non-member visibility denied; banned user 403.
    - Search communities: pagination respected; sort changes order; filter by category works.
    - Invite: duplicate invite prevented; non-existent user 404; valid invite 201.

27. Session 27 — `app/routers/search.py`
    - Typesense toggle: enabled uses client; disabled uses DB; client failure falls back safely.
    - Popular/recent cache: hit returns cached; miss populates; invalidation clears entries.
    - Suggestions API: enforces limit cap; empty query returns default; long query trimmed/validated.

28. Session 28 — `app/routers/admin_dashboard.py` & moderation
    - `/admin/users`: admin allowed; moderator denied; unauthenticated 401.
    - Ban/unban: ends_at None treated active; past date treated expired; future date enforced.
    - Audit log: creation on action; retrieval filtered by date range; sort descending by time.

29. Session 29 — `app/core/scheduling/tasks.py`
    - `_maybe_repeat_every`: in test returns None; in prod schedules; wrapper preserves __wrapped__.
    - `update_search_suggestions_task`: success updates; exception logged and reraised; db session closed.
    - Scheduler shutdown: shutdown handler stops jobs; second shutdown no error; state flag prevents double registration.

30. Session 30 — WS/notifications integration
    - WebSocket send flow: empty message triggers disconnect; text echoed via send_real_time_notification; exception path disconnects with reason.
    - `/notifications/subscribe`: rejects without token; accepts valid token once; duplicate subscription ignored.
    - Redis gateway broadcast: publish reaches local WS manager; Redis down logs and skips; message format preserved.
