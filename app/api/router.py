"""Centralized API router registration."""

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
    search,
    session,
    social_auth,
    statistics,
    sticker,
    support,
    user,
    vote,
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

# api_router.include_router(social_posts.router)  # Disabled pending module review
