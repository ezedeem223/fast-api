# Feature Flows

End-to-end feature workflows with key endpoints and responsibilities. Refer to
`docs/API_REFERENCE.md` for the full router inventory.

## Authentication and Sessions
- Register/login via `app/routers/auth.py`, `app/routers/oauth.py`, `app/routers/session.py`.
- Tokens are RSA-signed JWTs; refresh flow uses separate secret key.
- Session tracking and token blacklist live in user models.

## Posts, Comments, and Reactions
- Create/update/delete posts: `app/routers/post.py`.
- Comments and replies: `app/routers/comment.py`.
- Reactions and vote counts: `app/routers/reaction.py` and `app/routers/vote.py`.
- Reports for posts/comments: `app/routers/report.py` and `app/routers/comment.py`.

## Communities
- Community CRUD and membership: `app/routers/community.py`.
- Rules, invitations, and membership roles enforced in community service layer.
- Community posts reuse post creation flows with community context.

## Moderation and Reporting
- User warnings/bans and report reviews: `app/routers/moderation.py`.
- Report decisions can delete content or ignore with notes.
- IP bans and banned words are managed via moderation and banned words routers.

## Support Tickets
- Ticket creation and responses: `app/routers/support.py`.
- Status updates (open/in-progress/closed) require staff/admin role.

## Business Verification and Transactions
- Business registration: `POST /business/register`.
- Document upload: `POST /business/verify` (multipart).
- Admin review: `GET /business/verifications`, `PUT /business/verifications/{user_id}`.
- Business transactions are gated on verification status.

## Messaging, Calls, and Realtime
- Messaging endpoints in `app/routers/message.py`.
- Call signaling WebSocket: `app/routers/call_signaling.py`.
- Notifications WebSocket: `app/api/websocket.py`.

## Notifications
- Notification creation and delivery handled by `app/modules/notifications`.
- `app/notifications.py` remains as a compatibility shim for legacy imports.

## Fact Checking and Misinformation
- Fact submission and verification: `app/routers/fact_checking.py`.
- Amenhotep can answer from verified facts when DB is provided.

## Amenhotep AI
- WebSocket and HTTP entrypoints in `app/routers/amenhotep.py`.
- Knowledge base stored in `data/amenhotep/knowledge_base.json`.
- ONNX acceleration optional; falls back to PyTorch.
- Arabic prompts are answered in Modern Standard Arabic with a consistent style.
- Verified facts are surfaced with context and sources when a DB session is provided.

## Search and Analytics
- Search endpoints in `app/routers/search.py`.
- Analytics summaries in `app/routers/statistics.py` and `app/routers/admin_dashboard.py`.

## Media and Uploads
- Post uploads and audio/video handling in `app/routers/post.py`.
- Profile image upload in `app/routers/user.py`.
- File storage handled by `app/modules/utils/files.py`.
