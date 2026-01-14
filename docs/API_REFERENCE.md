# API Reference

Router-level endpoint inventory. Use this as a quick index; see router docstrings for details.

## Router Inventory

- Each router lists its prefix, tags, and endpoints.
- Paths are shown as `METHOD <prefix><path>`.

## app/routers/admin_dashboard.py

- Prefix: `/admin`
- Tags: Admin Dashboard

- `GET /admin/dashboard` - `admin_dashboard` - Main admin dashboard view.
- `GET /admin/stats` - `get_statistics` - Get overall system statistics.
- `GET /admin/fact-check/stats` - `get_fact_check_stats` - Fact-checking status counts and recent pending facts.
- `GET /admin/users` - `get_users` - Retrieve a list of users with optional sorting and filtering.
- `PUT /admin/users/{user_id}/role` - `update_user_role` - Update a user's role (e.g. moderator, admin).
- `GET /admin/reports/overview` - `get_reports_overview` - Get an overview of reports.
- `GET /admin/communities/overview` - `get_communities_overview` - Get an overview of communities.
- `GET /admin/user-activity/{user_id}` - `user_activity` - Retrieve user activity for a specified number of days.
- `GET /admin/problematic-users` - `problematic_users` - Retrieve a list of problematic users based on a threshold.
- `GET /admin/ban-statistics` - `ban_statistics` - Retrieve ban statistics.
- `GET /admin/ban-overview` - `get_ban_statistics_overview` - Retrieve an overview of ban statistics for the last 30 days.
- `GET /admin/common-ban-reasons` - `get_common_ban_reasons` - Retrieve common ban reasons with sorting options.
- `GET /admin/ban-effectiveness-trend` - `get_ban_effectiveness_trend` - Retrieve the trend of ban effectiveness over a specified number of days.
- `GET /admin/ban-type-distribution` - `get_ban_type_distribution` - Retrieve the distribution of different ban types over a specified period.

## app/routers/amenhotep.py

- Prefix: `/amenhotep`
- Tags: Amenhotep Chat

- `WEBSOCKET /amenhotep/ws/{user_id}` - `websocket_endpoint` - WebSocket endpoint for real-time chat with Amenhotep AI.
- `GET /amenhotep/chat-history/{user_id}` - `get_chat_history` - Retrieve the chat history for a specified user.
- `DELETE /amenhotep/clear-history/{user_id}` - `clear_chat_history` - Clear the chat history for a specified user.
- `POST /amenhotep/ask` - `ask_amenhotep` - HTTP endpoint to ask Amenhotep; validates empty input and applies language fallback.
- `WEBSOCKET /amenhotep/ws/amenhotep/{user_id}` - `amenhotep_chat` - Endpoint: amenhotep_chat.

## app/routers/auth.py

- Prefix: `/`
- Tags: Authentication

- `POST /register` - `register_user` - Register a new user using email/password and send a verification email.
- `POST /login` - `login` - User login endpoint.
- `POST /login/2fa` - `login_2fa` - Login with Two-Factor Authentication.
- `POST /logout` - `logout` - Logout endpoint.
- `POST /logout-all-devices` - `logout_all_devices` - Logout from all devices except the current session.
- `POST /invalidate-all-sessions` - `invalidate_all_sessions` - Invalidate (delete) all sessions for the current user.
- `POST /reset-password-request` - `reset_password_request` - Endpoint to request a password reset.
- `POST /reset-password` - `reset_password` - Reset the user's password after verifying the reset token.
- `POST /refresh-token` - `refresh_token` - Endpoint: refresh_token.
- `GET /jwks.json` - `jwks_keys` - Expose public keys for JWT verification (JWKS).
- `POST /verify-email` - `verify_email` - Endpoint: verify_email.
- `POST /resend-verification` - `resend_verification_email` - Resend the email verification link if the account exists and is not verified.
- `POST /change-email` - `change_email` - Change the user's email address.
- `POST /sessions/active` - `get_active_sessions` - Retrieve a list of active sessions for the current user.
- `DELETE /sessions/{session_id}` - `end_session` - End a specific session by session ID.
- `POST /password-strength` - `check_password_strength` - Endpoint: check_password_strength.
- `POST /change-password` - `change_password_auth` - Change the authenticated user's password after verifying the current password.
- `POST /security-questions` - `set_security_questions` - Set security questions for the user by encrypting the answers.
- `POST /verify-security-questions` - `verify_security_questions` - Verify the answers to the security questions.

## app/routers/banned_words.py

- Prefix: `/banned-words`
- Tags: Banned Words

- `POST /banned-words/` - `add_banned_word` - Add a single banned word.
- `GET /banned-words/` - `get_banned_words` - List banned words with optional filtering/sorting.
- `DELETE /banned-words/{word_id}` - `remove_banned_word` - Remove a banned word by ID.
- `PUT /banned-words/{word_id}` - `update_banned_word` - Update attributes of a banned word.
- `POST /banned-words/bulk` - `add_banned_words_bulk` - Bulk-insert banned words.

## app/routers/block.py

- Prefix: `/block`
- Tags: Block

- `POST /block/` - `block_user` - Block a user.
- `DELETE /block/{user_id}` - `manual_unblock_user` - Manually unblock a user.
- `GET /block/{user_id}` - `get_block_info` - Get information about a specific block.
- `GET /block/logs` - `get_block_logs` - Get block logs for the current user.
- `GET /block/current` - `get_currently_blocked_users` - Get a list of currently blocked users.
- `GET /block/statistics` - `get_block_statistics` - Get block statistics for the current user.
- `POST /block/appeal` - `create_block_appeal` - Create a new block appeal.
- `GET /block/appeals` - `get_block_appeals` - Get a list of pending block appeals.
- `PUT /block/appeal/{appeal_id}` - `review_block_appeal` - Review a block appeal.

## app/routers/business.py

- Prefix: `/business`
- Tags: Business

- `POST /business/register` - `register_business` - Register a new business account.
- `POST /business/verify` - `verify_business` - Verify a business account by uploading required documents.
- `POST /business/transactions` - `create_business_transaction` - Create a new business transaction.
- `GET /business/transactions` - `get_business_transactions` - Retrieve a list of business transactions for the current business user.
- `GET /business/verifications` - `list_business_verifications` - List business verification requests for admins.
- `PUT /business/verifications/{user_id}` - `review_business_verification` - Approve or reject a business verification request (admin only).

## app/routers/call.py

- Prefix: `/calls`
- Tags: Calls

- `POST /calls/` - `start_call` - Start a new call.
- `PUT /calls/{call_id}` - `update_call_status` - Update the status of an existing call.
- `GET /calls/active` - `get_active_calls` - Retrieve a list of active calls for the current user.
- `WEBSOCKET /calls/ws/{call_id}` - `websocket_endpoint` - WebSocket endpoint for call communication.

## app/routers/call_signaling.py

- Prefix: `/ws/call`
- Tags: Calls

- `WEBSOCKET /ws/call/{room_id}` - `signaling_ws` - Authenticated WebSocket for call signaling (owner or single-use join token).

## app/routers/category_management.py

- Prefix: `/categories`
- Tags: Categories

- `POST /categories/` - `create_category` - Create a new category.
- `PUT /categories/{category_id}` - `update_category` - Update an existing category.
- `DELETE /categories/{category_id}` - `delete_category` - Delete a category.
- `GET /categories/` - `get_categories` - Retrieve the list of main categories.

## app/routers/collaboration.py

- Prefix: `/collaboration`
- Tags: Collaboration

- `POST /collaboration/projects` - `create_project`
- `GET /collaboration/projects` - `list_projects`
- `GET /collaboration/projects/{project_id}` - `get_project`
- `POST /collaboration/projects/{project_id}/contributions` - `add_contribution`
- `GET /collaboration/projects/{project_id}/contributions` - `list_contributions`

## app/routers/comment.py

- Prefix: `/comments`
- Tags: Comments

- `POST /comments/` - `create_comment` - Create a new comment.
- `GET /comments/{post_id}` - `get_comments` - Retrieve comments for a post.
- `GET /comments/{comment_id}/replies` - `get_comment_replies` - Retrieve replies for a specific comment.
- `PUT /comments/{comment_id}` - `update_comment` - Update an existing comment.
- `DELETE /comments/{comment_id}` - `delete_comment` - Soft delete a comment.
- `GET /comments/{comment_id}/history` - `get_comment_edit_history` - Retrieve the edit history for a specific comment.
- `POST /comments/report` - `report_comment` - Report a post or comment.
- `POST /comments/{comment_id}/like` - `like_comment` - Like a comment.
- `PUT /comments/{comment_id}/highlight` - `highlight_comment` - Toggle the highlighted status of a comment.
- `PUT /comments/{comment_id}/best-answer` - `set_best_answer` - Set a comment as the best answer for a post.
- `PUT /comments/{comment_id}/pin` - `pin_comment` - Pin or unpin a comment on a post.

## app/routers/community.py

- Prefix: `/communities`
- Tags: Communities

- `POST /communities/` - `create_community` - Create a new community.
- `GET /communities/` - `get_communities` - Get list of communities with search and filter options.
- `GET /communities/{community_id}` - `get_community` - Get details of a specific community.
- `PUT /communities/{community_id}` - `update_community` - Update community information.
- `DELETE /communities/{community_id}` - `delete_community` - Delete a community (owner only).
- `POST /communities/{community_id}/join` - `join_community` - Join a community.
- `POST /communities/{community_id}/leave` - `leave_community` - Leave a community.
- `GET /communities/{community_id}/members` - `get_community_members` - Get list of community members.
- `PUT /communities/{community_id}/members/{user_id}/role` - `update_member_role` - Update member role in community.
- `DELETE /communities/{community_id}/members/{user_id}` - `remove_member` - Remove a member from community (moderators and owner only).
- `GET /communities/{community_id}/posts` - `get_community_posts` - Get community posts.
- `POST /communities/{community_id}/posts` - `create_community_post` - Create a post in the community.
- `POST /communities/{community_id}/post` - `create_community_post_legacy` - Legacy alias to support clients using /post instead of /posts for community posts.
- `POST /communities/{community_id}/invite` - `invite_to_community` - Invite a user to join the community.
- `GET /communities/invitations` - `get_my_invitations` - Get my community invitations.
- `POST /communities/invitations/{invitation_id}/accept` - `accept_invitation` - Accept a community invitation.
- `POST /communities/invitations/{invitation_id}/decline` - `decline_invitation` - Decline a community invitation.
- `GET /communities/{community_id}/stats` - `get_community_stats` - Get community statistics.
- `GET /communities/my/communities` - `get_my_communities` - Get communities I'm a member of.
- `GET /communities/my/owned` - `get_my_owned_communities` - Get communities I own.
- `PUT /communities/{community_id}/settings` - `update_community_settings` - Update community settings.

## app/routers/fact_checking.py

- Prefix: `/fact-checking`
- Tags: Fact Checking

- `POST /fact-checking/submit` - `submit_fact`
- `POST /fact-checking/verify/{fact_id}` - `verify_fact`
- `POST /fact-checking/correct/{fact_id}` - `correct_fact`
- `POST /fact-checking/vote/{fact_id}` - `vote_on_fact`
- `GET /fact-checking/facts/{fact_id}` - `get_fact` - Retrieve a fact by id.
- `GET /fact-checking/facts` - `list_facts`
- `GET /fact-checking/search` - `search_facts`
- `PUT /fact-checking/admin/override/{fact_id}` - `override_fact_status` - Allow admins to override fact status with an audit note.

## app/routers/follow.py

- Prefix: `/follow`
- Tags: Follow

- `POST /follow/{user_id}` - `follow_user` - Follow a user.
- `DELETE /follow/{user_id}` - `unfollow_user` - Unfollow a user.
- `GET /follow/followers` - `get_followers` - Retrieve a list of followers for the current user.
- `GET /follow/following` - `get_following` - Retrieve a list of users that the current user is following.
- `GET /follow/statistics` - `get_follow_statistics` - Retrieve follow statistics for the current user.
- `GET /follow/mutual` - `get_mutual_followers` - Retrieve a list of mutual followers for the current user.

## app/routers/hashtag.py

- Prefix: `/hashtags`
- Tags: Hashtags

- `POST /hashtags/` - `create_hashtag` - Create a new hashtag.
- `GET /hashtags/` - `get_hashtags` - Retrieve a list of hashtags.
- `POST /hashtags/follow/{hashtag_id}` - `follow_hashtag` - Follow a specific hashtag.
- `POST /hashtags/unfollow/{hashtag_id}` - `unfollow_hashtag` - Unfollow a specific hashtag.
- `GET /hashtags/trending` - `get_trending_hashtags` - Retrieve the most popular hashtags.
- `GET /hashtags/{hashtag_name}/posts` - `get_posts_by_hashtag` - Retrieve posts associated with a specific hashtag.
- `GET /hashtags/{hashtag_id}/statistics` - `get_hashtag_statistics` - Retrieve statistics for a specific hashtag.

## app/routers/impact.py

- Prefix: `/impact`
- Tags: Impact

- `POST /impact/certificates` - `create_certificate`
- `GET /impact/certificates` - `list_certificates`
- `POST /impact/cultural-dictionary` - `create_cultural_entry`
- `GET /impact/cultural-dictionary` - `list_cultural_entries`

## app/routers/message.py

- Prefix: `/message`
- Tags: Messages

- `POST /message/` - `create_message` - Create a new message with optional file attachments or sticker.
- `GET /message/` - `get_messages` - Retrieve messages for the current user.
- `PUT /message/{message_id}` - `update_message` - Update an existing message.
- `DELETE /message/{message_id}` - `delete_message` - Delete an existing message.
- `GET /message/conversations` - `get_conversations` - Retrieve the latest message from each conversation of the current user.
- `POST /message/location` - `send_location` - Send a location message.
- `POST /message/audio` - `create_audio_message` - Create an audio message.
- `GET /message/unread` - `get_unread_messages_count` - Retrieve the count of unread messages for the current user.
- `GET /message/statistics/{conversation_id}` - `get_conversation_statistics` - Retrieve statistics for a specific conversation.
- `PUT /message/{message_id}/read` - `mark_message_as_read` - Mark a specific message as read.
- `POST /message/send_file` - `send_file` - Send a file message.
- `GET /message/download/{file_name}` - `download_file` - Download a file message.
- `GET /message/inbox` - `get_inbox` - Retrieve the inbox messages for the current user.
- `GET /message/search` - `search_messages` - Search messages based on query, date range, message type, and conversation ID.
- `GET /message/{message_id}` - `get_message` - Retrieve a specific message by its ID.
- `POST /message/conversations` - `create_conversation` - Create a group conversation with the specified members.
- `GET /message/conversations` - `list_conversations` - List conversations the current user belongs to.
- `POST /message/conversations/{conversation_id}/members` - `add_conversation_members` - Add members to an existing conversation.
- `DELETE /message/conversations/{conversation_id}/members/{user_id}` - `remove_conversation_member` - Remove a member from the conversation.
- `POST /message/conversations/{conversation_id}/messages` - `send_group_message` - Send a new message to a conversation.
- `GET /message/conversations/{conversation_id}/messages` - `get_conversation_messages` - Retrieve messages for a given conversation.
- `PUT /message/user/read-status` - `update_read_status_visibility` - Update the user's preference for read status visibility.
- `WEBSOCKET /message/ws/amenhotep/{user_id}` - `amenhotep_chat` - Endpoint: amenhotep_chat.

## app/routers/moderation.py

- Prefix: `/moderation`
- Tags: Moderation

- `POST /moderation/warn/{user_id}` - `warn_user_route` - Warn a user.
- `POST /moderation/ban/{user_id}` - `ban_user_route` - Ban a user.
- `POST /moderation/unban/{user_id}` - `unban_user_route` - Lift a user's active ban.
- `PUT /moderation/reports/{report_id}/review` - `review_report` - Review a report submitted by users.
- `GET /moderation/reports` - `list_reports` - List reports filtered by status (moderators/admins only).
- `PUT /moderation/reports/{report_id}/decision` - `decide_report` - Resolve a report by deleting content or ignoring it with notes.
- `POST /moderation/ip` - `ban_ip` - Ban an IP address.
- `GET /moderation/ip` - `get_banned_ips` - Retrieve a list of banned IP addresses.
- `DELETE /moderation/ip/{ip_address}` - `unban_ip` - Unban an IP address.

## app/routers/moderator.py

- Prefix: `/moderator`
- Tags: Moderator

- `GET /moderator/community/{community_id}/reports` - `get_community_reports` - Return reports for a community, optionally filtered by status.
- `PUT /moderator/reports/{report_id}` - `update_report` - Update a report's status and resolution notes.
- `GET /moderator/community/{community_id}/members` - `get_community_members` - List members of a community for moderator review.
- `PUT /moderator/community/{community_id}/member/{user_id}/role` - `update_member_role` - Update a member's role (admin or moderator only).

## app/routers/notifications.py

- Prefix: `/notifications`
- Tags: Notifications

- `GET /notifications/` - `get_notifications` - Get the list of notifications for the current user.
- `POST /notifications/subscribe` - `subscribe_notifications` - Lightweight subscribe endpoint for WS/push style notifications.
- `GET /notifications/unread-count` - `get_unread_count` - Get the count of unread notifications.
- `GET /notifications/summary` - `get_notification_summary` - Return aggregate counts for unread/unseen notifications.
- `GET /notifications/feed` - `get_notification_feed` - Cursor-paginated notification feed that marks fetched items as seen.
- `PUT /notifications/{notification_id}/read` - `mark_notification_as_read` - Mark a specific notification as read.
- `PUT /notifications/mark-all-read` - `mark_all_notifications_as_read` - Mark all notifications as read.
- `DELETE /notifications/{notification_id}` - `delete_notification` - Delete a specific notification.
- `PUT /notifications/{notification_id}/archive` - `archive_notification` - Archive a specific notification.
- `DELETE /notifications/clear-all` - `clear_all_notifications` - Clear all read notifications.
- `GET /notifications/preferences` - `get_notification_preferences` - Get user's notification preferences.
- `PUT /notifications/preferences` - `update_notification_preferences` - Update notification preferences.
- `POST /notifications/send-bulk` - `send_bulk_notifications` - Send bulk notifications (admin only).
- `PUT /notifications/bulk-mark-read` - `bulk_mark_as_read` - Mark multiple notifications as read.
- `DELETE /notifications/bulk-delete` - `bulk_delete_notifications` - Delete multiple notifications.
- `POST /notifications/schedule` - `schedule_notification` - Schedule a notification to be sent later.
- `GET /notifications/scheduled` - `get_scheduled_notifications` - Get scheduled notifications.
- `DELETE /notifications/scheduled/{notification_id}` - `cancel_scheduled_notification` - Cancel a scheduled notification.
- `POST /notifications/register-device` - `register_device_token` - Register a device token for push notifications.
- `DELETE /notifications/unregister-device` - `unregister_device_token` - Unregister a device token.
- `POST /notifications/test-push` - `test_push_notification` - Send a test push notification.
- `GET /notifications/analytics` - `get_notification_analytics` - Get notification analytics.
- `GET /notifications/analytics/delivery-stats` - `get_delivery_statistics` - Get delivery statistics.
- `GET /notifications/analytics/engagement` - `get_engagement_metrics` - Get engagement metrics.
- `GET /notifications/groups` - `get_notification_groups` - Get grouped notifications.
- `PUT /notifications/groups/{group_id}/expand` - `expand_notification_group` - Expand a notification group to show all notifications.
- `GET /notifications/admin/stats` - `get_system_notification_stats` - Get system-wide notification statistics (admin only).
- `POST /notifications/admin/retry-failed` - `retry_failed_notifications` - Retry failed notifications (admin only).
- `GET /notifications/admin/delivery-logs` - `get_delivery_logs` - Get delivery logs (admin only).

## app/routers/oauth.py

- Prefix: `/`
- Tags: OAuth

- `GET /google` - `auth_google`
- `GET /google/callback` - `auth_google_callback`
- `GET /facebook` - `auth_facebook`
- `GET /facebook/callback` - `auth_facebook_callback`
- `GET /twitter` - `auth_twitter`
- `GET /twitter/callback` - `auth_twitter_callback`

## app/routers/p2fa.py

- Prefix: `/2fa`
- Tags: Two Factor Authentication

- `POST /2fa/enable` - `enable_2fa` - Enable two-factor authentication for the current user.
- `POST /2fa/disable` - `disable_2fa` - Disable two-factor authentication for the current user.
- `POST /2fa/verify` - `verify_2fa` - Verify the provided OTP for two-factor authentication.

## app/routers/post.py

- Prefix: `/posts`
- Tags: Posts

- `GET /posts/search` - `search_posts` - Search for posts based on keyword/category/hashtag filters.
- `GET /posts/{id}` - `get_post` - Retrieve a single post and related aggregates.
- `POST /posts/` - `create_posts` - Create a new post after validating content and triggering side-effects (emails/broadcast/cache bust).
- `GET /posts/scheduled` - `get_scheduled_posts` - Retrieve scheduled posts for the authenticated user.
- `POST /posts/upload_file/` - `upload_file` - Handle file uploads and create a post pointing to the stored media.
- `POST /posts/report/` - `report_post` - Report a post or comment with a given reason. Also, flag the content if offensive text is detected.
- `DELETE /posts/{id}` - `delete_post` - Delete a post if the requester is the owner.
- `PUT /posts/{id}` - `update_post` - Update an existing post with new content; invalidates cached lists/details.
- `POST /posts/short_videos/` - `create_short_video` - Create a short video post.
- `GET /posts/recommendations/` - `get_recommendations` - Return post recommendations by combining followed and other posts.
- `GET /posts/{post_id}/comments` - `get_comments` - Retrieve comments for a specific post ordered by pinning and creation date.
- `POST /posts/repost/{post_id}` - `repost` - Create a repost of an existing post.
- `GET /posts/post/{post_id}/repost-stats` - `get_repost_statistics` - Retrieve repost statistics for a specific post.
- `GET /posts/reposts/{post_id}` - `get_reposts` - Retrieve reposts for a given original post.
- `GET /posts/top-reposts` - `get_top_reposts` - Retrieve top repost statistics ordered by repost count.
- `PUT /posts/toggle-reposts/{post_id}` - `toggle_allow_reposts` - Toggle the allow_reposts flag for a given post.
- `POST /posts/{id}/analyze` - `analyze_existing_post` - Analyze an existing post to update its sentiment, sentiment score, and content suggestion.
- `GET /posts/mentions` - `get_posts_with_mentions` - Retrieve posts where the current user is mentioned.
- `GET /posts/memories/daily` - `discover_daily_memories` - 1.3 Rediscovery: Get 'On This Day' memories (cached per user for 1h).
- `GET /posts/users/{user_id}/timeline` - `get_user_evolution_timeline` - 1.2 Dynamic Timeline: Get user evolution timeline.
- `POST /posts/audio` - `create_audio_post` - Create an audio post by saving the uploaded audio file,
- `GET /posts/audio` - `get_audio_posts` - Retrieve posts that are audio posts, ordered by creation date.
- `POST /posts/poll` - `create_poll_post` - Create a poll post along with its options and optional end date.
- `POST /posts/{post_id}/vote` - `vote_in_poll` - Record a vote for a poll option in a poll post.
- `GET /posts/{post_id}/poll-results` - `get_poll_results` - Retrieve the results of a poll post including vote counts and percentages.
- `PUT /posts/{id}/archive` - `archive_post` - Toggle the archived status of a post.
- `GET /posts/` - `get_posts` - Retrieve posts along with aggregated vote counts; optional translation controlled by query flag.
- `GET /posts/{id}/export-pdf` - `export_post_as_pdf` - Export a specific post as a PDF file.

## app/routers/reaction.py

- Prefix: `/reactions`
- Tags: Reactions

- `POST /reactions/` - `create_reaction` - Create or update a reaction on a post or comment.
- `GET /reactions/post/{post_id}` - `get_post_reaction_counts` - Retrieve the count of reactions for a specific post grouped by reaction type.
- `GET /reactions/comment/{comment_id}` - `get_comment_reaction_counts` - Retrieve the count of reactions for a specific comment grouped by reaction type.

## app/routers/reels.py

- Prefix: `/reels`
- Tags: Reels

- `POST /reels/` - `create_reel`
- `GET /reels/active` - `list_reels`
- `POST /reels/{reel_id}/view` - `increment_reel_views`
- `DELETE /reels/{reel_id}` - `delete_reel`

## app/routers/report.py

- Prefix: `/report`
- Tags: Reports

- `POST /report/` - `create_report`

## app/routers/screen_share.py

- Prefix: `/screen-share`
- Tags: Screen Share

- `POST /screen-share/start` - `start_screen_share` - Start a new screen sharing session for a call.
- `POST /screen-share/end` - `end_screen_share` - End an active screen sharing session.
- `PUT /screen-share/update` - `update_screen_share` - Update an existing screen share session.
- `WEBSOCKET /screen-share/ws/{call_id}` - `screen_share_websocket` - WebSocket endpoint for real-time screen sharing data transmission.

## app/routers/search.py

- Prefix: `/search`
- Tags: Search

- `POST /search/` - `search` - Main search endpoint.
- `GET /search/advanced` - `advanced_search` - Advanced search endpoint for posts.
- `GET /search/categories` - `get_categories` - Endpoint: get_categories.
- `GET /search/authors` - `get_authors` - Endpoint: get_authors.
- `GET /search/autocomplete` - `autocomplete` - Return autocomplete suggestions for a given query.
- `POST /search/record-search` - `record_search` - Record a user's search term.
- `GET /search/popular` - `popular_searches` - Get the most popular search queries.
- `GET /search/recent` - `recent_searches` - Get the most recent search queries.
- `GET /search/trends` - `search_trends` - Endpoint: search_trends.
- `GET /search/smart` - `smart_search` - Smart search using user search history and behavior.

## app/routers/session.py

- Prefix: `/sessions`
- Tags: Encrypted Sessions

- `POST /sessions/` - `create_encrypted_session` - Create a new encrypted session between the current user and another user.
- `PUT /sessions/{session_id}` - `update_encrypted_session` - Update the encrypted session data for the current user.

## app/routers/social_auth.py

- Prefix: `/`
- Tags: Social Authentication

- `GET /login/facebook` - `login_facebook` - Redirect the user to Facebook's OAuth login page.
- `GET /auth/facebook` - `auth_facebook` - Handle Facebook OAuth callback.
- `GET /login/twitter` - `login_twitter` - Redirect the user to Twitter's OAuth login page.
- `GET /auth/twitter` - `auth_twitter` - Handle Twitter OAuth callback.
- `GET /callback/{platform}` - `social_callback` - Handle OAuth callback for social platforms (Reddit or LinkedIn).
- `DELETE /disconnect/{platform}` - `disconnect_social_account` - Disconnect a social media account from the current user.

## app/routers/statistics.py

- Prefix: `/statistics`
- Tags: Statistics

- `GET /statistics/vote-analytics` - `get_vote_analytics` - Retrieve vote analytics for the current user.
- `GET /statistics/comments` - `get_comment_statistics` - Retrieve statistics about comments.
- `GET /statistics/ban-overview` - `get_ban_statistics_overview` - Provide an overview of ban statistics for the last 30 days.
- `GET /statistics/common-ban-reasons` - `get_common_ban_reasons` - Retrieve a list of the most common ban reasons.
- `GET /statistics/ban-effectiveness-trend` - `get_ban_effectiveness_trend` - Retrieve the trend of ban effectiveness scores over a specified number of days.
- `GET /statistics/ban-type-distribution` - `get_ban_type_distribution` - Retrieve the distribution of different ban types (IP bans, word bans, user bans)
- `GET /statistics/top-posts` - `get_top_posts` - Return the most engaging posts ranked by votes and comment counts.
- `GET /statistics/top-users` - `get_top_users` - Return the most active community members based on followers and publishing activity.

## app/routers/sticker.py

- Prefix: `/stickers`
- Tags: Stickers

- `POST /stickers/pack` - `create_sticker_pack` - Create a new sticker pack.
- `POST /stickers/` - `create_sticker` - Create a new sticker within a sticker pack.
- `GET /stickers/pack/{pack_id}` - `get_sticker_pack` - Endpoint: get_sticker_pack.
- `GET /stickers/` - `get_stickers` - Endpoint: get_stickers.
- `GET /stickers/search` - `search_stickers` - Endpoint: search_stickers.
- `GET /stickers/emojis` - `get_emojis` - Endpoint: get_emojis.
- `PUT /stickers/{sticker_id}/approve` - `approve_sticker` - Approve a sticker.
- `POST /stickers/category` - `create_sticker_category` - Create a new sticker category.
- `POST /stickers/report` - `report_sticker` - Report a sticker for a specified reason.
- `GET /stickers/reports` - `get_sticker_reports` - Retrieve all sticker reports.
- `GET /stickers/categories` - `get_sticker_categories` - Endpoint: get_sticker_categories.
- `GET /stickers/category/{category_id}` - `get_stickers_by_category` - Endpoint: get_stickers_by_category.
- `PUT /stickers/{sticker_id}/disable` - `disable_sticker` - Disable (hide) a sticker from listings.
- `PUT /stickers/{sticker_id}/enable` - `enable_sticker` - Re-enable a sticker.

## app/routers/support.py

- Prefix: `/support`
- Tags: Support

- `POST /support/tickets` - `create_ticket` - Create a new support ticket.
- `GET /support/tickets` - `get_user_tickets` - Retrieve all support tickets created by the current user.
- `POST /support/tickets/{ticket_id}/responses` - `add_ticket_response` - Add a response to an existing support ticket.
- `PUT /support/tickets/{ticket_id}/status` - `update_ticket_status` - Update the status of a support ticket (support staff/admin only).

## app/routers/user.py

- Prefix: `/users`
- Tags: Users

- `POST /users/` - `create_user` - Create a new user and send an email notification.
- `GET /users/users/{user_id}/followers` - `get_user_followers` - Retrieve a list of followers with sorting options.
- `PUT /users/users/me/followers-settings` - `update_followers_settings` - Update user's followers settings.
- `PUT /users/public-key` - `update_public_key` - Update the user's public key.
- `GET /users/{id}` - `get_user` - Get user details by ID.
- `POST /users/verify` - `verify_user` - Upload verification document and verify the user.
- `GET /users/my-content` - `get_user_content` - Retrieve the user's content including posts, comments, articles, and reels.
- `PUT /users/profile` - `update_user_profile` - Update the user's profile.
- `PUT /users/privacy` - `update_privacy_settings` - Update the user's privacy settings.
- `GET /users/profile/{user_id}` - `get_user_profile` - Get the user profile and translate bio if needed.
- `GET /users/profile/{user_id}/posts` - `get_user_posts` - Get posts of a user by user ID.
- `GET /users/profile/{user_id}/articles` - `get_user_articles` - Get articles of a user by user ID.
- `GET /users/profile/{user_id}/media` - `get_user_media` - Get media posts of a user by user ID.
- `GET /users/profile/{user_id}/likes` - `get_user_likes` - Get posts liked by the user.
- `POST /users/profile/image` - `upload_profile_image` - Upload the user's profile image.
- `POST /users/change-password` - `change_password` - Change the user's password.
- `POST /users/enable-2fa` - `enable_2fa` - Enable Two-Factor Authentication.
- `POST /users/verify-2fa` - `verify_2fa` - Verify the Two-Factor Authentication code.
- `POST /users/disable-2fa` - `disable_2fa` - Disable Two-Factor Authentication.
- `POST /users/logout-all-devices` - `logout_all_devices` - Log out the user from all other devices.
- `GET /users/sessions` - `list_sessions` - List active sessions for the current user.
- `DELETE /users/sessions/{session_id}` - `revoke_session` - Terminate a specific session and blacklist its token.
- `GET /users/suggested-follows` - `get_suggested_follows` - Get suggested users to follow based on shared interests and connections.
- `GET /users/analytics` - `get_user_analytics` - Get user analytics for a specified period.
- `GET /users/settings` - `get_user_settings` - Get user settings (UI and notification settings).
- `PUT /users/settings` - `update_user_settings` - Update the user's settings.
- `PUT /users/block-settings` - `update_block_settings` - Update the user's block settings.
- `PUT /users/settings/reposts` - `update_repost_settings` - Update the user's repost settings.
- `GET /users/notifications` - `get_user_notifications` - Retrieve the user's notifications.
- `PUT /users/notifications/{notification_id}/read` - `mark_notification_as_read` - Mark a specific notification as read.
- `POST /users/users/{user_id}/suspend` - `suspend_user` - Suspend the user for a specified number of days.
- `POST /users/users/{user_id}/unsuspend` - `unsuspend_user` - Unsuspend the user.
- `PUT /users/users/me/language` - `update_user_language` - Update the user's preferred language and auto-translate settings.
- `GET /users/languages` - `get_language_options` - Endpoint: get_language_options.
- `GET /users/me/export` - `export_my_data` - Export all user-related data.
- `DELETE /users/me` - `delete_my_account` - Delete the current user's account and related data.
- `POST /users/me/identities` - `link_identity` - Link another account as a private identity.
- `GET /users/me/identities` - `list_identities` - List all linked identities.
- `DELETE /users/me/identities/{linked_user_id}` - `remove_identity` - Unlink a previously linked identity.

## app/routers/vote.py

- Prefix: `/vote`
- Tags: Vote

- `POST /vote/` - `vote` - Create or update a reaction on a post.
- `DELETE /vote/{post_id}` - `remove_reaction` - Remove a reaction from a post.
- `GET /vote/{post_id}` - `get_vote_count` - Get the vote count for a given post.
- `GET /vote/{post_id}/voters` - `get_post_voters` - Retrieve the list of users who voted on the post.

## app/routers/wellness.py

- Prefix: `/wellness`
- Tags: Wellness

- `GET /wellness/metrics` - `get_wellness_metrics` - Return current wellness metrics for the authenticated user.
- `POST /wellness/goals` - `create_wellness_goal`
- `POST /wellness/do-not-disturb` - `enable_do_not_disturb`
- `POST /wellness/mental-health-mode` - `enable_mental_health_mode`

