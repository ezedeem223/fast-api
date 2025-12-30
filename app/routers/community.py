"""Community router for membership, rules, invitations, and analytics endpoints.

Handles join/leave, invites, rule management, caching hooks, and analytics. Auth required
for mutating endpoints; read endpoints may be public depending on service layer policy.
"""

from typing import Any, Dict, List, Optional

from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.core.cache.redis_cache import cache, cache_manager  # Cache helpers.
from app.core.database import get_db
from app.services.community.service import CommunityService
from fastapi import (
    APIRouter,
    BackgroundTasks,
    Body,
    Depends,
    HTTPException,
    Query,
    status,
)

from .. import models, oauth2, schemas
from ..notifications import queue_email_notification  # noqa: F401
from ..notifications import schedule_email_notification  # noqa: F401

router = APIRouter(prefix="/communities", tags=["Communities"])


class InvitationRequest(BaseModel):
    user_id: int


def get_community_service(db: Session = Depends(get_db)) -> CommunityService:
    """Endpoint: get_community_service."""
    return CommunityService(db)


# ==========================================
# Community CRUD Operations
# ==========================================


@router.post(
    "/", status_code=status.HTTP_201_CREATED, response_model=schemas.CommunityOut
)
async def create_community(
    community_data: Dict[str, Any] = Body(...),
    current_user: models.User = Depends(oauth2.get_current_user),
    service: CommunityService = Depends(get_community_service),
):
    """Create a new community."""
    # Validate and create community
    community = schemas.CommunityCreate(**community_data)

    new_community = service.create_community(
        current_user=current_user,
        payload=community,
    )

    # Invalidate cache
    await cache_manager.invalidate("communities:list:*")

    return schemas.CommunityOut.model_validate(new_community)


@router.get(
    "/",
    response_model=List[schemas.CommunityOut],
    summary="Get list of communities",
)
@cache(
    prefix="communities:list", ttl=180, include_user=False
)  # Cache response for performance.
async def get_communities(
    current_user: models.User = Depends(oauth2.get_current_user),
    service: CommunityService = Depends(get_community_service),
    skip: int = Query(0, ge=0),
    limit: int = Query(20, ge=1, le=100),
    search: Optional[str] = None,
    category: Optional[str] = None,
    is_active: Optional[bool] = None,
    sort_by: str = Query("created_at", enum=["created_at", "member_count", "name"]),
    order: str = Query("desc", enum=["asc", "desc"]),
):
    """Get list of communities with search and filter options."""
    communities = service.get_communities(
        skip=skip,
        limit=limit,
        search=search,
        category=category,
        is_active=is_active,
        sort_by=sort_by,
        order=order,
    )

    return [schemas.CommunityOut.model_validate(c) for c in communities]


@router.get("/{community_id}", response_model=schemas.CommunityDetailOut)
@cache(
    prefix="community:detail", ttl=120, include_user=False
)  # Cache response for performance.
async def get_community(
    community_id: int,
    current_user: models.User = Depends(oauth2.get_current_user),
    service: CommunityService = Depends(get_community_service),
):
    """Get details of a specific community."""
    community = service.get_community_or_404(community_id)

    # Check if user has access
    if not community.is_active and community.owner_id != current_user.id:
        if not service.is_member(community_id, current_user.id):
            raise HTTPException(
                status_code=403,
                detail="This community is inactive and you are not a member",
            )

    return schemas.CommunityDetailOut.model_validate(community)


@router.put("/{community_id}", response_model=schemas.CommunityOut)
async def update_community(
    community_id: int,
    community_update: schemas.CommunityUpdate,
    current_user: models.User = Depends(oauth2.get_current_user),
    service: CommunityService = Depends(get_community_service),
):
    """Update community information."""
    updated_community = service.update_community(
        community_id=community_id,
        payload=community_update,
        current_user=current_user,
    )

    # Invalidate caches
    await cache_manager.invalidate("communities:list:*")
    await cache_manager.invalidate(f"community:detail:*{community_id}*")

    return schemas.CommunityOut.model_validate(updated_community)


@router.delete("/{community_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_community(
    community_id: int,
    current_user: models.User = Depends(oauth2.get_current_user),
    service: CommunityService = Depends(get_community_service),
):
    """Delete a community (owner only)."""
    service.delete_community(
        community_id=community_id,
        current_user=current_user,
    )

    # Invalidate caches
    await cache_manager.invalidate("communities:list:*")
    await cache_manager.invalidate(f"community:detail:*{community_id}*")

    return None


# ==========================================
# Community Membership
# ==========================================


@router.post("/{community_id}/join", response_model=dict)
async def join_community(
    community_id: int,
    current_user: models.User = Depends(oauth2.get_current_user),
    service: CommunityService = Depends(get_community_service),
):
    """Join a community."""
    member = service.join_community(
        community_id=community_id,
        current_user=current_user,
    )

    # Invalidate caches
    await cache_manager.invalidate("communities:list:*")
    await cache_manager.invalidate(f"community:detail:*{community_id}*")
    await cache_manager.invalidate(f"community:members:*{community_id}*")

    return member


@router.post("/{community_id}/leave", status_code=status.HTTP_204_NO_CONTENT)
async def leave_community(
    community_id: int,
    current_user: models.User = Depends(oauth2.get_current_user),
    service: CommunityService = Depends(get_community_service),
):
    """Leave a community."""
    service.leave_community(
        community_id=community_id,
        current_user=current_user,
    )

    # Invalidate caches
    await cache_manager.invalidate("communities:list:*")
    await cache_manager.invalidate(f"community:detail:*{community_id}*")
    await cache_manager.invalidate(f"community:members:*{community_id}*")

    return None


@router.get("/{community_id}/members", response_model=List[schemas.CommunityMemberOut])
@cache(
    prefix="community:members", ttl=120, include_user=False
)  # Cache response for performance.
async def get_community_members(
    community_id: int,
    current_user: models.User = Depends(oauth2.get_current_user),
    service: CommunityService = Depends(get_community_service),
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=100),
    role: Optional[str] = None,
):
    """Get list of community members."""
    members = service.get_members(
        community_id=community_id,
        skip=skip,
        limit=limit,
        role=role,
    )

    return [schemas.CommunityMemberOut.model_validate(m) for m in members]


@router.put(
    "/{community_id}/members/{user_id}/role", response_model=schemas.CommunityMemberOut
)
async def update_member_role(
    community_id: int,
    user_id: int,
    role_update: schemas.MemberRoleUpdate,
    current_user: models.User = Depends(oauth2.get_current_user),
    service: CommunityService = Depends(get_community_service),
):
    """Update member role in community."""
    updated_member = service.update_member_role(
        community_id=community_id,
        user_id=user_id,
        new_role=role_update.role,
        current_user=current_user,
    )

    # Invalidate caches
    await cache_manager.invalidate(f"community:members:*{community_id}*")
    await cache_manager.invalidate(f"community:detail:*{community_id}*")

    return schemas.CommunityMemberOut.model_validate(updated_member)


@router.delete(
    "/{community_id}/members/{user_id}", status_code=status.HTTP_204_NO_CONTENT
)
async def remove_member(
    community_id: int,
    user_id: int,
    current_user: models.User = Depends(oauth2.get_current_user),
    service: CommunityService = Depends(get_community_service),
):
    """Remove a member from community (moderators and owner only)."""
    service.remove_member(
        community_id=community_id,
        user_id=user_id,
        current_user=current_user,
    )

    # Invalidate caches
    await cache_manager.invalidate(f"community:members:*{community_id}*")
    await cache_manager.invalidate(f"community:detail:*{community_id}*")

    return None


# ==========================================
# Community Posts
# ==========================================


@router.get("/{community_id}/posts", response_model=List[schemas.PostOut])
@cache(
    prefix="community:posts", ttl=60, include_user=False
)  # Cache response for performance.
async def get_community_posts(
    community_id: int,
    current_user: models.User = Depends(oauth2.get_current_user),
    service: CommunityService = Depends(get_community_service),
    skip: int = Query(0, ge=0),
    limit: int = Query(20, ge=1, le=100),
    sort_by: str = Query("created_at", enum=["created_at", "votes", "comments"]),
    order: str = Query("desc", enum=["asc", "desc"]),
):
    """Get community posts."""
    posts = service.get_community_posts(
        community_id=community_id,
        skip=skip,
        limit=limit,
        sort_by=sort_by,
        order=order,
    )

    return [schemas.PostOut.model_validate(p) for p in posts]


@router.post(
    "/{community_id}/posts",
    status_code=status.HTTP_201_CREATED,
    response_model=schemas.PostOut,
)
async def create_community_post(
    community_id: int,
    post_data: schemas.PostCreate,
    background_tasks: BackgroundTasks,
    current_user: models.User = Depends(oauth2.get_current_user),
    service: CommunityService = Depends(get_community_service),
):
    """Create a post in the community."""
    new_post = service.create_community_post(
        community_id=community_id,
        payload=post_data,
        current_user=current_user,
    )

    # Invalidate caches
    await cache_manager.invalidate(f"community:posts:*{community_id}*")
    await cache_manager.invalidate("posts:list:*")

    return schemas.PostOut.model_validate(new_post)


@router.post(
    "/{community_id}/post",
    status_code=status.HTTP_201_CREATED,
    response_model=schemas.PostOut,
)
async def create_community_post_legacy(
    community_id: int,
    post_data: schemas.PostCreate,
    current_user: models.User = Depends(oauth2.get_current_user),
    service: CommunityService = Depends(get_community_service),
):
    """
    Legacy alias to support clients using /post instead of /posts for community posts.
    """
    new_post = service.create_community_post(
        community_id=community_id,
        payload=post_data,
        current_user=current_user,
    )

    # Invalidate caches
    await cache_manager.invalidate(f"community:posts:*{community_id}*")
    await cache_manager.invalidate("posts:list:*")

    return schemas.PostOut.model_validate(new_post)


# ==========================================
# Community Invitations
# ==========================================


@router.post("/{community_id}/invite", response_model=schemas.CommunityInvitationOut)
async def invite_to_community(
    community_id: int,
    invitation_data: InvitationRequest,
    current_user: models.User = Depends(oauth2.get_current_user),
    service: CommunityService = Depends(get_community_service),
):
    """Invite a user to join the community."""
    invitation = service.create_invitation(
        community_id=community_id,
        invited_user_id=invitation_data.user_id,
        inviter=current_user,
    )

    return schemas.CommunityInvitationOut.model_validate(invitation)


@router.get("/invitations", response_model=List[schemas.CommunityInvitationOut])
async def get_my_invitations(
    current_user: models.User = Depends(oauth2.get_current_user),
    service: CommunityService = Depends(get_community_service),
    skip: int = Query(0, ge=0),
    limit: int = Query(20, ge=1, le=100),
    status: Optional[str] = None,
):
    """Get my community invitations."""
    invitations = service.get_user_invitations(
        user_id=current_user.id,
        skip=skip,
        limit=limit,
        status=status,
    )

    return [schemas.CommunityInvitationOut.model_validate(i) for i in invitations]


@router.post(
    "/invitations/{invitation_id}/accept", response_model=schemas.CommunityMemberOut
)
async def accept_invitation(
    invitation_id: int,
    current_user: models.User = Depends(oauth2.get_current_user),
    service: CommunityService = Depends(get_community_service),
):
    """Accept a community invitation."""
    member = service.accept_invitation(
        invitation_id=invitation_id,
        user=current_user,
    )

    # Invalidate caches
    community_id = member.community_id
    await cache_manager.invalidate(f"community:members:*{community_id}*")
    await cache_manager.invalidate(f"community:detail:*{community_id}*")

    return schemas.CommunityMemberOut.model_validate(member)


@router.post(
    "/invitations/{invitation_id}/decline", status_code=status.HTTP_204_NO_CONTENT
)
async def decline_invitation(
    invitation_id: int,
    current_user: models.User = Depends(oauth2.get_current_user),
    service: CommunityService = Depends(get_community_service),
):
    """Decline a community invitation."""
    service.decline_invitation(
        invitation_id=invitation_id,
        user=current_user,
    )

    return None


# ==========================================
# Community Statistics
# ==========================================


@router.get("/{community_id}/stats", response_model=schemas.CommunityStatsOut)
async def get_community_stats(
    community_id: int,
    current_user: models.User = Depends(oauth2.get_current_user),
    service: CommunityService = Depends(get_community_service),
    days: int = Query(30, ge=1, le=365),
):
    """Get community statistics."""
    stats = service.get_community_stats(
        community_id=community_id,
        days=days,
    )

    return schemas.CommunityStatsOut(**stats)


# ==========================================
# User's Communities
# ==========================================


@router.get("/my/communities", response_model=List[schemas.CommunityOut])
async def get_my_communities(
    current_user: models.User = Depends(oauth2.get_current_user),
    service: CommunityService = Depends(get_community_service),
    skip: int = Query(0, ge=0),
    limit: int = Query(20, ge=1, le=100),
    role: Optional[str] = None,
):
    """Get communities I'm a member of."""
    communities = service.get_user_communities(
        user_id=current_user.id,
        skip=skip,
        limit=limit,
        role=role,
    )

    return [schemas.CommunityOut.model_validate(c) for c in communities]


@router.get("/my/owned", response_model=List[schemas.CommunityOut])
async def get_my_owned_communities(
    current_user: models.User = Depends(oauth2.get_current_user),
    service: CommunityService = Depends(get_community_service),
    skip: int = Query(0, ge=0),
    limit: int = Query(20, ge=1, le=100),
):
    """Get communities I own."""
    communities = service.get_owned_communities(
        owner_id=current_user.id,
        skip=skip,
        limit=limit,
    )

    return [schemas.CommunityOut.model_validate(c) for c in communities]


# ==========================================
# Community Settings
# ==========================================


@router.put("/{community_id}/settings", response_model=schemas.CommunityOut)
async def update_community_settings(
    community_id: int,
    settings_update: schemas.CommunitySettingsUpdate,
    current_user: models.User = Depends(oauth2.get_current_user),
    service: CommunityService = Depends(get_community_service),
):
    """Update community settings."""
    updated_community = service.update_settings(
        community_id=community_id,
        settings=settings_update,
        current_user=current_user,
    )

    # Invalidate caches
    await cache_manager.invalidate(f"community:detail:*{community_id}*")

    return schemas.CommunityOut.model_validate(updated_community)
