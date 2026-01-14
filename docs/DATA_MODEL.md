# Data Model Overview

This document summarizes the core data model and how major domains relate. The
source of truth is the SQLAlchemy models in `app/modules/**/models.py`.

## Users and Identity
- `User`: central actor; owns posts/comments, receives notifications, can be a business.
- Roles: `UserRole` (admin/moderator/user) plus convenience flags on `User`.
- Sessions: `UserSession`, `TokenBlacklist` track sessions and invalidated tokens.
- Privacy: `PrivacyLevel`, `followers_visibility`, and per-user settings fields.

## Social Content
- `Post`: primary content unit; can belong to a community and carry media metadata.
- `Comment`: threaded replies on posts; supports reactions, highlights, and soft delete.
- `Reaction`: reactions on posts or comments; ties to `User` and target content.
- `Vote`: legacy post vote model; used in some analytics and scoring paths.
- `Hashtag`: many-to-many with posts and user follows.

## Communities
- `Community`: container for posts, rules, membership, and analytics.
- `CommunityMember`: join/role state for each user in a community.
- `CommunityRule`, `CommunityInvitation`, `CommunityStatistics`, `Tag`, `Category`:
  supporting tables for rules, invites, analytics, and classification.

## Moderation and Reporting
- `Report`: abuse report for a post/comment with status and review metadata.
- `UserWarning`, `UserBan`, `BanStatistics`, `BanReason`: warning/ban history and aggregates.
- `IPBan`, `BannedWord`: IP and word-level enforcement.
- `Block`, `BlockLog`, `BlockAppeal`: user-to-user blocking and appeal workflow.

## Notifications and Realtime
- `Notification`: persisted notification with delivery logs and preferences.
- `NotificationPreferences`: per-user channel and category settings.
- Realtime state is tracked in memory/Redis by `ConnectionManager` (not persisted).

## Messaging and Calls
- `Message`, `Conversation`, `ConversationMember`: messaging threads and membership.
- `Call`, `CallParticipant`, `ScreenShareSession`, `EncryptedCall`: realtime call records.

## Business and Commerce
- `BusinessTransaction`: business engagements between two users.
- Business verification lives on `User` (documents + verification status).

## Support and Helpdesk
- `SupportTicket`: user-submitted ticket with status.
- `TicketResponse`: threaded responses on a ticket.

## Fact Checking and Misinformation
- `Fact`: submitted claim with status and evidence.
- `FactVerification`, `FactCorrection`, `FactVote`: verification workflow.
- `CredibilityBadge`: trust markers for verified facts.
- `MisinformationWarning`: warning attached to posts/comments.

## Media, Wellness, and Misc Domains
- `Sticker`, `StickerCategory`: stickers and associations for posts/comments.
- `WellnessCheckIn`, `WellnessAlert`: wellness tracking and alerts.
- `ImpactCertificate`, `CulturalDictionaryEntry`: auxiliary social-impact features.

## Cross-Cutting Relationships
- User owns posts/comments, follows users, can be reported, and receives notifications.
- Posts belong to communities, accumulate comments/reactions, and can be reported.
- Reports link reporters to reported users and target content (post/comment).
- Facts can link to source posts/comments for verification provenance.

## Canonical Model Sources
- `app/modules/users/models.py`
- `app/modules/posts/models.py`
- `app/modules/community/models.py`
- `app/modules/social/models.py`
- `app/modules/moderation/models.py`
- `app/modules/notifications/models.py`
- `app/modules/messaging/models.py`
- `app/modules/fact_checking/models.py`
- `app/modules/support/models.py`
