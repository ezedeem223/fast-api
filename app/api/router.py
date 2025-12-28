"""Centralized API router registration with feature grouping.

Groups:
- Core user-generated content: posts, comments, votes, follows, blocks.
- Auth/OAuth/sessions: auth, oauth, social_auth, session, p2fa.
- Community/moderation/admin: communities, hashtags, reactions, moderators, category management, stats, moderation tools.
- Messaging/calls/realtime: message, call, screen_share, call_signaling, notifications, reels.
- Business/support/impact: business, support, impact.
- Utilities and AI: search, amenhotep, fact_checking, wellness, collaboration, sticker, report.
"""

from fastapi import APIRouter

from app.routers import (
    admin_dashboard,
    amenhotep,
    banned_words,
    block,
    business,
    call,
    category_management,
    comment,
    community,
    follow,
    hashtag,
    message,
    fact_checking,
    moderation,
    moderator,
    auth,
    oauth,
    p2fa,
    notifications,
    reels,
    post,
    reaction,
    report,
    screen_share,
    call_signaling,
    search,
    session,
    social_auth,
    statistics,
    sticker,
    support,
    user,
    vote,
    wellness,
    collaboration,
    impact,
)

api_router = APIRouter()

# Core feature routers
api_router.include_router(post.router)
api_router.include_router(user.router)
api_router.include_router(auth.router)
api_router.include_router(vote.router)
api_router.include_router(comment.router)
api_router.include_router(follow.router)
api_router.include_router(block.router)

# Administrative and moderation features
api_router.include_router(admin_dashboard.router)
api_router.include_router(moderator.router)
api_router.include_router(moderation.router)
api_router.include_router(category_management.router)
api_router.include_router(statistics.router)

# Authentication / OAuth / sessions
api_router.include_router(oauth.router)
api_router.include_router(social_auth.router)
api_router.include_router(session.router)

# Community and engagement modules
api_router.include_router(community.router)
api_router.include_router(hashtag.router)
api_router.include_router(reaction.router)
api_router.include_router(message.router)
api_router.include_router(call.router)
api_router.include_router(screen_share.router)
api_router.include_router(call_signaling.router)
api_router.include_router(notifications.router)
api_router.include_router(reels.router)

# Business and support
api_router.include_router(business.router)
api_router.include_router(support.router)

# Media, stickers, and auxiliary services
api_router.include_router(sticker.router)
api_router.include_router(p2fa.router)
api_router.include_router(report.router)
api_router.include_router(search.router)
api_router.include_router(banned_words.router)
api_router.include_router(amenhotep.router)
api_router.include_router(fact_checking.router)
api_router.include_router(wellness.router)
api_router.include_router(collaboration.router)
api_router.include_router(impact.router)

# api_router.include_router(social_posts.router)  # Disabled pending module review
