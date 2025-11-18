# =====================================================
# ==================== Imports ========================
# =====================================================
from fastapi import (
    APIRouter,
    Depends,
    HTTPException,
    status,
    Query,
    Body,
)
from fastapi import BackgroundTasks as FastAPIBackgroundTasks
from sqlalchemy.orm import Session
from typing import Any, Dict, List, Optional
from datetime import date
from http import HTTPStatus
import logging
from fastapi.responses import StreamingResponse

# Local imports
from .. import models, schemas, oauth2
from pydantic import ValidationError
from app.schemas import (
    CommunityAnalytics,
    CommunityCreate,
    CommunityInvitationCreate,
    CommunityInvitationOut,
    CommunityInvitationResponse,
    CommunityMemberOut,
    CommunityMemberUpdate,
    CommunityOut,
    CommunityRuleCreate,
    CommunityRuleOut,
    CommunityUpdate,
)
from app.core.database import get_db
from app.services.community import CommunityService
from app.notifications import (
    queue_email_notification as _queue_email_notification,
    schedule_email_notification as _schedule_email_notification,
)

# Expose BackgroundTasks for backwards compatibility (tests patch it directly).
BackgroundTasks = FastAPIBackgroundTasks


def queue_email_notification(*args, **kwargs):
    """Proxy to the notifications helper so tests can patch this module attribute."""
    return _queue_email_notification(*args, **kwargs)


def schedule_email_notification(*args, **kwargs):
    """Proxy to the notifications helper so tests can patch this module attribute."""
    return _schedule_email_notification(*args, **kwargs)
logger = logging.getLogger(__name__)

HTTP_422_UNPROCESSABLE_CONTENT = getattr(
    status, "HTTP_422_UNPROCESSABLE_CONTENT", HTTPStatus.UNPROCESSABLE_ENTITY
)
router = APIRouter(prefix="/communities", tags=["Communities"])


def get_community_service(db: Session = Depends(get_db)) -> CommunityService:
    return CommunityService(db)

# =====================================================
# =============== Helper Utility Functions ==============
# =====================================================
def update_community_statistics(db: Session, community_id: int):
    """
    Update the community statistics.

    Returns:
        The updated CommunityStatistics record.
    """
    service = CommunityService(db)
    return service.update_community_statistics(community_id=community_id)


# =====================================================
# ==================== Community Endpoints ============
# =====================================================


@router.post(
    "/",
    status_code=status.HTTP_201_CREATED,
    response_model=CommunityOut,
    summary="Create a new community",
    description="Create a new community with the ability to specify category and tags.",
)
async def create_community(
    community_data: Dict[str, Any] = Body(..., description="Community payload"),
    current_user: models.User = Depends(oauth2.get_current_user),
    service: CommunityService = Depends(get_community_service),
):
    """
    Create a new community with permission checks and basic settings.
    """
    try:
        logger.info("Incoming community payload: %s", community_data)
        community_data.setdefault("category_id", None)
        community_data.setdefault("tags", [])
        community = CommunityCreate.model_validate(community_data)
    except ValidationError as exc:
        raise HTTPException(
            status_code=HTTP_422_UNPROCESSABLE_CONTENT,
            detail=exc.errors(),
        ) from exc
    new_community = service.create_community(
        current_user=current_user,
        payload=community,
    )

    return CommunityOut.model_validate(new_community)


@router.get(
    "/",
    response_model=List[CommunityOut],
    summary="Get list of communities",
    description="Search and filter communities with sorting options.",
)
async def get_communities(
    current_user: models.User = Depends(oauth2.get_current_user),
    service: CommunityService = Depends(get_community_service),
    skip: int = Query(0, ge=0, description="Number of items to skip"),
    limit: int = Query(100, ge=1, le=100, description="Number of items to return"),
    search: str = Query("", description="Search text"),
    category_id: Optional[int] = Query(None, description="Category ID"),
    sort_by: str = Query(
        "created_at",
        description="Sort criterion",
        enum=["created_at", "members_count", "activity"],
    ),
    sort_order: str = Query("desc", description="Sort order", enum=["asc", "desc"]),
):
    """
    Retrieve a list of communities with search and filter options.
    """
    communities = await service.list_communities(
        current_user=current_user,
        skip=skip,
        limit=limit,
        search=search or "",
        category_id=category_id,
        sort_by=sort_by,
        sort_order=sort_order,
    )

    return [CommunityOut.model_validate(community) for community in communities]


@router.get(
    "/{id}",
    response_model=CommunityOut,
    summary="Get specific community details",
)
async def get_community(
    id: int,
    current_user: models.User = Depends(oauth2.get_current_user),
    service: CommunityService = Depends(get_community_service),
):
    """
    Retrieve detailed information of a specific community along with its related data.
    """
    community = await service.get_community(community_id=id, current_user=current_user)
    return CommunityOut.model_validate(community)


@router.put(
    "/{id}",
    response_model=CommunityOut,
    summary="Update community information",
)
async def update_community(
    id: int,
    updated_community: CommunityUpdate,
    current_user: models.User = Depends(oauth2.get_current_user),
    service: CommunityService = Depends(get_community_service),
):
    """
    Update community information with proper authorization.

    Parameters:
      - id: ID of the community to update.
      - updated_community: CommunityUpdate schema with new community data.
      - db: Database session.
      - current_user: The current authenticated user.

    Process:
      - Verify community existence.
      - Check user permissions.
      - Update category, tags, and rules if provided.
      - Update other community data and timestamp.
      - Log the event and create a notification.

    Returns:
      The updated community data.
    """
    community = service.update_community(
        community_id=id,
        payload=updated_community,
        current_user=current_user,
    )

    return CommunityOut.model_validate(community)


@router.post(
    "/{id}/join",
    status_code=status.HTTP_200_OK,
    summary="Join a community",
)
async def join_community(
    id: int,
    current_user: models.User = Depends(oauth2.get_current_user),
    service: CommunityService = Depends(get_community_service),
):
    """
    Join a community with permission checks.

    Process:
      - Verify community existence.
      - Check if the user is already a member.
      - For private communities, verify an invitation exists.
      - Add the user as a member and update community and member counts.
      - Update invitation status if applicable.
      - Send a notification to the community owner.

    Returns:
      A confirmation message.
    """
    return service.join_community(
        community_id=id,
        current_user=current_user,
    )


@router.post(
    "/{community_id}/leave",
    status_code=status.HTTP_200_OK,
    summary="Leave a community",
)
async def leave_community(
    community_id: int,
    current_user: models.User = Depends(oauth2.get_current_user),
    service: CommunityService = Depends(get_community_service),
):
    """
    Leave a community after validating membership constraints.

    Process:
      - Ensure the community exists and the user is a member.
      - Prevent owners from leaving their own communities.
      - Remove the membership record and notify the owner.

    Returns:
      A confirmation message.
    """
    return service.leave_community(
        community_id=community_id,
        current_user=current_user,
    )


@router.post(
    "/{community_id}/post",
    status_code=status.HTTP_201_CREATED,
    response_model=schemas.PostOut,
    summary="Create a new post in the community",
)
async def create_community_post(
    community_id: int,
    post: schemas.PostCreate,
    current_user: models.User = Depends(oauth2.get_current_user),
    service: CommunityService = Depends(get_community_service),
):
    """
    Create a new post in the community with content validation and permission checks.

    Process:
      - Perform membership and content validation inside the service layer.
      - Persist the new post and trigger VIP promotions/notifications if applicable.

    Returns:
      The created post.
    """
    new_post = service.create_community_post(
        community_id=community_id,
        payload=post,
        current_user=current_user,
    )
    return schemas.PostOut.model_validate(new_post)


@router.post(
    "/{community_id}/rules",
    response_model=CommunityRuleOut,
    summary="Add a new rule to the community",
)
async def add_community_rule(
    community_id: int,
    rule: CommunityRuleCreate,
    current_user: models.User = Depends(oauth2.get_current_user),
    service: CommunityService = Depends(get_community_service),
):
    """
    Add a new rule to the community with proper permission checks.
    """
    new_rule = service.add_community_rule(
        community_id=community_id,
        payload=rule,
        current_user=current_user,
    )
    return CommunityRuleOut.model_validate(new_rule)


@router.get(
    "/{community_id}/analytics",
    response_model=CommunityAnalytics,
    summary="Comprehensive community analytics",
)
async def get_community_analytics(
    community_id: int,
    start_date: date,
    end_date: date,
    current_user: models.User = Depends(oauth2.get_current_user),
    service: CommunityService = Depends(get_community_service),
):
    """
    Retrieve detailed analytics for the community.
    """
    analytics = service.get_community_analytics(
        community_id=community_id,
        start_date=start_date,
        end_date=end_date,
        current_user=current_user,
    )
    return CommunityAnalytics.model_validate(analytics)


@router.put(
    "/{community_id}/members/{user_id}/role",
    response_model=CommunityMemberOut,
    summary="Update a member's role in the community",
)
async def update_member_role(
    community_id: int,
    user_id: int,
    role_update: CommunityMemberUpdate,
    current_user: models.User = Depends(oauth2.get_current_user),
    service: CommunityService = Depends(get_community_service),
):
    """
    Update a member's role in the community after verifying permissions.

    Parameters:
      - community_id: ID of the community.
      - user_id: ID of the member to update.
      - role_update: CommunityMemberUpdate schema with the new role.
      - db: Database session.
      - current_user: The current authenticated user.

    Returns:
      The updated community member information.
    """
    member = service.update_member_role(
        community_id=community_id,
        user_id=user_id,
        payload=role_update,
        current_user=current_user,
    )

    return CommunityMemberOut.model_validate(member)


@router.post(
    "/{community_id}/invitations",
    status_code=status.HTTP_201_CREATED,
    response_model=CommunityInvitationOut,
    summary="Invite new members to the community",
)
async def invite_members(
    community_id: int,
    invitations: List[CommunityInvitationCreate],
    current_user: models.User = Depends(oauth2.get_current_user),
    service: CommunityService = Depends(get_community_service),
):
    """
    Invite new members to the community after verifying permissions and limits.

    Parameters:
      - community_id: ID of the community.
      - invitations: A list of CommunityInvitationCreate schemas.
      - db: Database session.
      - current_user: The current authenticated user.

    Returns:
      A list of created community invitations.
    """
    created_invitations = service.invite_members(
        community_id=community_id,
        invitations=invitations,
        current_user=current_user,
    )
    return [CommunityInvitationOut.model_validate(inv) for inv in created_invitations]


@router.post(
    "/invitations/{invitation_id}/respond",
    status_code=status.HTTP_200_OK,
    summary="Respond to a community invitation",
)
async def respond_to_invitation(
    invitation_id: int,
    response: CommunityInvitationResponse,
    current_user: models.User = Depends(oauth2.get_current_user),
    service: CommunityService = Depends(get_community_service),
):
    """
    Accept or decline a pending community invitation.

    Process:
      - Ensure the invitation exists and belongs to the authenticated user.
      - Validate the invitation status and community availability.
      - Join the community on acceptance or record the decline.

    Returns:
      A confirmation message describing the outcome.
    """
    return service.respond_to_invitation(
        invitation_id=invitation_id,
        current_user=current_user,
        accept=response.accept,
    )


@router.post(
    "/invitations/cleanup",
    status_code=status.HTTP_200_OK,
    summary="Clean up expired community invitations",
)
async def cleanup_invitations_endpoint(
    current_user: models.User = Depends(oauth2.get_current_user),
    service: CommunityService = Depends(get_community_service),
):
    """
    Mark pending invitations that have passed their expiry date as expired.

    Returns:
      The number of invitations that were updated.
    """
    expired = service.cleanup_expired_invitations()
    return {"expired_invitations": expired}


@router.get(
    "/{community_id}/export",
    response_class=StreamingResponse,
    summary="Export community data",
)
async def export_community_data(
    community_id: int,
    data_type: str = Query(..., enum=["members", "posts", "analytics"]),
    date_from: Optional[date] = None,
    date_to: Optional[date] = None,
    current_user: models.User = Depends(oauth2.get_current_user),
    service: CommunityService = Depends(get_community_service),
):
    """
    Export community data in CSV format.

    Parameters:
      - community_id: ID of the community.
      - data_type: Type of data to export (members, posts, or analytics).
      - date_from: Start date for filtering data.
      - date_to: End date for filtering data.
      - db: Database session.
      - current_user: The current authenticated user.

    Returns:
      A StreamingResponse containing the CSV data.
    """
    csv_data, filename = service.export_community_data(
        community_id=community_id,
        data_type=data_type,
        current_user=current_user,
        date_from=date_from,
        date_to=date_to,
    )
    headers = {"Content-Disposition": f"attachment; filename={filename}"}
    return StreamingResponse(
        iter([csv_data]),
        media_type="text/csv",
        headers=headers,
    )


# ==================== Notification Handling ====================


# ==================== Periodic Tasks ====================


async def cleanup_expired_invitations(db: Session):
    """
    Clean up expired community invitations.
    """
    service = CommunityService(db)
    return service.cleanup_expired_invitations()


async def update_community_rankings(db: Session):
    """
    Update community rankings based on various metrics.
    """
    service = CommunityService(db)
    service.update_community_rankings()
