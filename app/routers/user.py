"""User router covering profile, preferences, followers, language, and session endpoints."""

from fastapi import (
    status,
    HTTPException,
    Depends,
    APIRouter,
    BackgroundTasks,
    UploadFile,
    File,
    Query,
    Response,
)
from sqlalchemy.orm import Session
from typing import List


# Importing local modules
from .. import models, schemas, oauth2
from app.modules.users import UserService
from app.modules.users.models import User
from app.modules.users.schemas import IdentityLinkCreate, IdentityOut, DataExportOut
from app.core.database import get_db
from ..notifications import send_email_notification
from app.modules.utils.events import log_user_event
from ..i18n import (
    ALL_LANGUAGES,
    get_translated_content,
)  # Assuming get_translated_content is defined here
from app.core.cache.redis_cache import cache, cache_manager


router = APIRouter(prefix="/users", tags=["Users"])


def get_user_service(db: Session = Depends(get_db)) -> UserService:
    """Endpoint: get_user_service."""
    return UserService(db)


# --- User Endpoints ---


@router.post("/", status_code=status.HTTP_201_CREATED, response_model=schemas.UserOut)
async def create_user(
    background_tasks: BackgroundTasks,
    user: schemas.UserCreate,
    service: UserService = Depends(get_user_service),
):
    """Create a new user and send an email notification."""
    new_user = service.create_user(user)

    # Send email notification asynchronously
    background_tasks.add_task(
        send_email_notification,
        to=new_user.email,
        subject="New User Created",
        body=f"A new user with email {new_user.email} has been created.",
    )

    return new_user


@router.get("/users/{user_id}/followers", response_model=schemas.FollowersListOut)
@cache(prefix="user_profile", ttl=300)
async def get_user_followers(
    user_id: int,
    service: UserService = Depends(get_user_service),
    current_user: User = Depends(oauth2.get_current_user),
    sort_by: schemas.SortOption = Query(schemas.SortOption.DATE),
    order: str = Query("desc", enum=["asc", "desc"]),
    skip: int = 0,
    limit: int = 100,
):
    """Retrieve a list of followers with sorting options."""
    _, followers, total_count = service.get_user_followers(
        user_id=user_id,
        requesting_user=current_user,
        sort_by=sort_by,
        order=order,
        skip=skip,
        limit=limit,
    )

    return {
        "followers": [
            schemas.FollowerOut(
                id=follow.follower.id,
                username=follow.follower.username,
                follow_date=follow.created_at,
                post_count=follow.follower.post_count,
                interaction_count=follow.follower.interaction_count,
            )
            for follow in followers
        ],
        "total_count": total_count,
    }


@router.put(
    "/users/me/followers-settings", response_model=schemas.UserFollowersSettings
)
async def update_followers_settings(
    settings: schemas.UserFollowersSettings,
    service: UserService = Depends(get_user_service),
    current_user: User = Depends(oauth2.get_current_user),
):
    """Update user's followers settings."""
    return service.update_followers_settings(current_user, settings)


@router.put("/public-key", response_model=schemas.UserOut)
def update_public_key(
    key_update: schemas.UserPublicKeyUpdate,
    service: UserService = Depends(get_user_service),
    current_user: User = Depends(oauth2.get_current_user),
):
    """Update the user's public key."""
    return service.update_public_key(current_user, key_update)


@router.get("/{id}", response_model=schemas.UserOut)
@cache(prefix="user:profile", ttl=300, include_user=False)  # Cache response for performance.
async def get_user(
    id: int,
    service: UserService = Depends(get_user_service),
    current_user: User = Depends(oauth2.get_current_user),
):
    """Get user details by ID."""
    user = service.get_user_or_404(id)

    # Check privacy settings for profile
    if user.privacy_level == models.PrivacyLevel.PRIVATE and user.id != current_user.id:
        raise HTTPException(status_code=403, detail="This profile is private")

    if user.privacy_level == models.PrivacyLevel.CUSTOM:
        allowed_users = user.custom_privacy.get("allowed_users", [])
        if current_user.id not in allowed_users and user.id != current_user.id:
            raise HTTPException(
                status_code=403, detail="You don't have permission to view this profile"
            )

    return user


@router.post("/verify")
async def verify_user(
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    current_user: User = Depends(oauth2.get_current_user),
    service: UserService = Depends(get_user_service),
):
    """Upload verification document and verify the user."""
    service.verify_user_document(current_user, file)

    await send_email_notification(
        to=current_user.email,
        subject="Verification Completed",
        body="Your account has been verified successfully.",
    )

    return {"info": "Verification document uploaded and user verified successfully."}


@router.get("/my-content", response_model=schemas.UserContentOut)
async def get_user_content(
    service: UserService = Depends(get_user_service),
    current_user: User = Depends(oauth2.get_current_user),
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=100),
):
    """Retrieve the user's content including posts, comments, articles, and reels."""
    return service.get_user_content(current_user, skip, limit)


@router.put("/profile", response_model=schemas.UserProfileOut)
async def update_user_profile(
    profile_update: schemas.UserProfileUpdate,
    service: UserService = Depends(get_user_service),
    current_user: User = Depends(oauth2.get_current_user),
):
    """Update the user's profile."""
    updated_profile = service.update_profile(current_user, profile_update)
    log_user_event(service.db, current_user.id, "update_profile")

    # Invalidate user cache
    await cache_manager.invalidate(f"user:profile:*{current_user.id}*")

    return updated_profile


@router.put("/privacy", response_model=schemas.UserOut)
def update_privacy_settings(
    privacy_settings: schemas.UserPrivacyUpdate,
    service: UserService = Depends(get_user_service),
    current_user: User = Depends(oauth2.get_current_user),
):
    """Update the user's privacy settings."""
    return service.update_privacy_settings(current_user, privacy_settings)


@router.get("/profile/{user_id}", response_model=schemas.UserProfileOut)
async def get_user_profile(
    user_id: int,
    service: UserService = Depends(get_user_service),
    current_user: User = Depends(oauth2.get_current_user),
):
    """Get the user profile and translate bio if needed."""
    user, metrics = service.get_profile_overview(user_id)
    translated_bio = await get_translated_content(user.bio, current_user, user.language)

    return schemas.UserProfileOut(
        id=user.id,
        email=user.email,
        profile_image=user.profile_image,
        bio=translated_bio,
        location=user.location,
        website=user.website,
        joined_at=user.joined_at,
        post_count=metrics["post_count"],
        follower_count=metrics["follower_count"],
        following_count=metrics["following_count"],
        community_count=metrics["community_count"],
        media_count=metrics["media_count"],
    )


@router.get("/profile/{user_id}/posts", response_model=List[schemas.PostOut])
def get_user_posts(
    user_id: int,
    service: UserService = Depends(get_user_service),
    skip: int = 0,
    limit: int = 10,
):
    """Get posts of a user by user ID."""
    return service.get_user_posts(user_id, skip, limit)


@router.get("/profile/{user_id}/articles", response_model=List[schemas.ArticleOut])
def get_user_articles(
    user_id: int,
    service: UserService = Depends(get_user_service),
    skip: int = 0,
    limit: int = 10,
):
    """Get articles of a user by user ID."""
    return service.get_user_articles(user_id, skip, limit)


@router.get("/profile/{user_id}/media", response_model=List[schemas.PostOut])
def get_user_media(
    user_id: int,
    service: UserService = Depends(get_user_service),
    skip: int = 0,
    limit: int = 10,
):
    """Get media posts of a user by user ID."""
    return service.get_user_media(user_id, skip, limit)


@router.get("/profile/{user_id}/likes", response_model=List[schemas.PostOut])
def get_user_likes(
    user_id: int,
    service: UserService = Depends(get_user_service),
    skip: int = 0,
    limit: int = 10,
):
    """Get posts liked by the user."""
    return service.get_user_likes(user_id, skip, limit)


@router.post("/profile/image")
async def upload_profile_image(
    file: UploadFile = File(...),
    current_user: User = Depends(oauth2.get_current_user),
    service: UserService = Depends(get_user_service),
):
    """Upload the user's profile image."""
    service.upload_profile_image(current_user, file)

    # Invalidate user cache
    await cache_manager.invalidate(f"user:profile:*{current_user.id}*")

    return {"info": "Profile image uploaded successfully."}


@router.post("/change-password")
def change_password(
    password_change: schemas.PasswordChange,
    current_user: User = Depends(oauth2.get_current_user),
    service: UserService = Depends(get_user_service),
):
    """Change the user's password."""
    return service.change_password(current_user, password_change)


@router.post("/enable-2fa", response_model=schemas.Enable2FAResponse)
def enable_2fa(
    current_user: User = Depends(oauth2.get_current_user),
    service: UserService = Depends(get_user_service),
):
    """Enable Two-Factor Authentication."""
    return service.enable_2fa(current_user)


@router.post("/verify-2fa")
def verify_2fa(
    otp: str,
    current_user: User = Depends(oauth2.get_current_user),
    service: UserService = Depends(get_user_service),
):
    """Verify the Two-Factor Authentication code."""
    return service.verify_2fa(current_user, otp)


@router.post("/disable-2fa")
def disable_2fa(
    current_user: User = Depends(oauth2.get_current_user),
    service: UserService = Depends(get_user_service),
):
    """Disable Two-Factor Authentication."""
    return service.disable_2fa(current_user)


@router.post("/logout-all-devices")
def logout_all_devices(
    current_user: User = Depends(oauth2.get_current_user),
    current_session: str = Depends(oauth2.get_current_session),
    service: UserService = Depends(get_user_service),
):
    """Log out the user from all other devices."""
    return service.logout_other_sessions(current_user, current_session)


@router.get("/suggested-follows", response_model=List[schemas.UserOut])
def get_suggested_follows(
    service: UserService = Depends(get_user_service),
    current_user: User = Depends(oauth2.get_current_user),
    limit: int = 10,
):
    """Get suggested users to follow based on shared interests and connections."""
    return service.get_suggested_follows(current_user, limit)


@router.get("/analytics", response_model=schemas.UserAnalytics)
async def get_user_analytics(
    service: UserService = Depends(get_user_service),
    current_user: User = Depends(oauth2.get_current_user),
    days: int = Query(30, ge=1, le=365),
):
    """Get user analytics for a specified period."""
    return service.get_user_analytics(current_user, days)


@router.get("/settings", response_model=schemas.UserSettings)
async def get_user_settings(
    current_user: User = Depends(oauth2.get_current_user),
    service: UserService = Depends(get_user_service),
):
    """Get user settings (UI and notification settings)."""
    return service.get_user_settings(current_user)


@router.put("/settings", response_model=schemas.UserSettings)
async def update_user_settings(
    settings: schemas.UserSettingsUpdate,
    current_user: User = Depends(oauth2.get_current_user),
    service: UserService = Depends(get_user_service),
):
    """Update the user's settings."""
    return service.update_user_settings(current_user, settings)


@router.put("/block-settings", response_model=schemas.UserOut)
async def update_block_settings(
    settings: schemas.BlockSettings,
    service: UserService = Depends(get_user_service),
    current_user: User = Depends(oauth2.get_current_user),
):
    """Update the user's block settings."""
    return service.update_block_settings(current_user, settings)


@router.put("/settings/reposts", response_model=schemas.UserOut)
def update_repost_settings(
    settings: schemas.UserUpdate,
    service: UserService = Depends(get_user_service),
    current_user: User = Depends(oauth2.get_current_user),
):
    """Update the user's repost settings."""
    return service.update_repost_settings(current_user, settings)


@router.get("/notifications", response_model=List[schemas.NotificationOut])
def get_user_notifications(
    service: UserService = Depends(get_user_service),
    current_user: User = Depends(oauth2.get_current_user),
    skip: int = 0,
    limit: int = 10,
):
    """Retrieve the user's notifications."""
    return service.get_user_notifications(current_user, skip, limit)


@router.put(
    "/notifications/{notification_id}/read", response_model=schemas.NotificationOut
)
def mark_notification_as_read(
    notification_id: int,
    service: UserService = Depends(get_user_service),
    current_user: User = Depends(oauth2.get_current_user),
):
    """Mark a specific notification as read."""
    return service.mark_notification_as_read(notification_id, current_user)


@router.post("/users/{user_id}/suspend")
def suspend_user(
    user_id: int,
    days: int,
    service: UserService = Depends(get_user_service),
):
    """Suspend the user for a specified number of days."""
    return service.suspend_user(user_id, days)


@router.post("/users/{user_id}/unsuspend")
def unsuspend_user(
    user_id: int,
    service: UserService = Depends(get_user_service),
):
    """Unsuspend the user."""
    return service.unsuspend_user(user_id)


@router.put("/users/me/language")
def update_user_language(
    language: schemas.UserLanguageUpdate,
    service: UserService = Depends(get_user_service),
    current_user: User = Depends(oauth2.get_current_user),
):
    """Update the user's preferred language and auto-translate settings."""
    return service.update_language_preferences(current_user, language)


@router.get("/languages")
def get_language_options():
    """Endpoint: get_language_options."""
    return [{"code": code, "name": name} for code, name in ALL_LANGUAGES.items()]

@router.get("/me/export", response_model=DataExportOut)
def export_my_data(
    service: UserService = Depends(get_user_service),
    current_user: User = Depends(oauth2.get_current_user),
):
    """Export all user-related data."""
    return service.export_user_data(current_user)


@router.delete("/me", status_code=204)
def delete_my_account(
    service: UserService = Depends(get_user_service),
    current_user: User = Depends(oauth2.get_current_user),
):
    """Delete the current user's account and related data."""
    service.delete_account(current_user)
    return Response(status_code=204)


@router.post("/me/identities", response_model=IdentityOut, status_code=201)
def link_identity(
    payload: IdentityLinkCreate,
    service: UserService = Depends(get_user_service),
    current_user: User = Depends(oauth2.get_current_user),
):
    """Link another account as a private identity."""
    return service.link_identity(
        current_user, payload.linked_user_id, payload.relationship_type
    )


@router.get("/me/identities", response_model=List[IdentityOut])
def list_identities(
    service: UserService = Depends(get_user_service),
    current_user: User = Depends(oauth2.get_current_user),
):
    """List all linked identities."""
    return service.list_identities(current_user)


@router.delete("/me/identities/{linked_user_id}", status_code=204)
def remove_identity(
    linked_user_id: int,
    service: UserService = Depends(get_user_service),
    current_user: User = Depends(oauth2.get_current_user),
):
    """Unlink a previously linked identity."""
    service.remove_identity(current_user, linked_user_id)
    return Response(status_code=204)
