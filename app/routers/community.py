"""
Community Router Module
This module provides endpoints for managing communities, including creation, retrieval, updating,
membership management, content management, analytics, data export, and notification handling.
"""

# =====================================================
# ==================== Imports ========================
# =====================================================
from fastapi import (
    APIRouter,
    Depends,
    HTTPException,
    status,
    Query,
    Request,
    Body,
    Response,
    BackgroundTasks,
)
from sqlalchemy.orm import Session, joinedload
from sqlalchemy import func, or_, desc, asc
from typing import List, Union, Optional
from datetime import date, timedelta, datetime, timezone
import logging
import emoji
from fastapi.responses import HTMLResponse, StreamingResponse
import csv
from io import StringIO

# Local imports
from .. import models, schemas, oauth2
from ..database import get_db
from ..utils import (
    log_user_event,
    create_notification,
    get_translated_content,
    check_content_against_rules,
    check_for_profanity,
    validate_urls,
    analyze_sentiment,
    is_valid_image_url,
    is_valid_video_url,
    detect_language,
    update_post_score,
)
from ..config import settings

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/communities", tags=["Communities"])

# =====================================================
# =============== Global Constants ====================
# =====================================================
MAX_PINNED_POSTS = 5
MAX_RULES = 20
ACTIVITY_THRESHOLD_VIP = 1000
INACTIVE_DAYS_THRESHOLD = 30


# =====================================================
# =============== Helper Utility Functions ==============
# =====================================================
def check_community_permissions(
    user: models.User,
    community: models.Community,
    required_role: models.CommunityRole,
) -> bool:
    """
    Verify that the user has the required permissions in the community.

    Raises:
        HTTPException: If the community does not exist or the user lacks the required role.
    """
    if not community:
        raise HTTPException(status_code=404, detail="Community not found")

    member = next((m for m in community.members if m.user_id == user.id), None)
    if not member:
        raise HTTPException(
            status_code=403,
            detail="You must be a member of the community to perform this action",
        )

    if member.role not in [
        required_role,
        models.CommunityRole.ADMIN,
        models.CommunityRole.OWNER,
    ]:
        raise HTTPException(
            status_code=403,
            detail="You do not have sufficient permissions to perform this action",
        )

    return True


def update_community_statistics(db: Session, community_id: int):
    """
    Update the community statistics.

    Returns:
        The updated CommunityStatistics record.
    """
    today = date.today()

    stats = (
        db.query(models.CommunityStatistics)
        .filter(
            models.CommunityStatistics.community_id == community_id,
            models.CommunityStatistics.date == today,
        )
        .first()
    )

    if not stats:
        stats = models.CommunityStatistics(community_id=community_id, date=today)
        db.add(stats)

    stats.member_count = (
        db.query(models.CommunityMember)
        .filter(models.CommunityMember.community_id == community_id)
        .count()
    )

    stats.post_count = (
        db.query(models.Post)
        .filter(
            models.Post.community_id == community_id,
            func.date(models.Post.created_at) == today,
        )
        .count()
    )

    stats.comment_count = (
        db.query(models.Comment)
        .join(models.Post)
        .filter(
            models.Post.community_id == community_id,
            func.date(models.Comment.created_at) == today,
        )
        .count()
    )

    stats.active_users = (
        db.query(models.CommunityMember)
        .filter(
            models.CommunityMember.community_id == community_id,
            models.CommunityMember.last_active_at >= today - timedelta(days=30),
        )
        .count()
    )

    stats.total_reactions = (
        db.query(func.count(models.Vote.id))
        .join(models.Post)
        .filter(
            models.Post.community_id == community_id,
            func.date(models.Vote.created_at) == today,
        )
        .scalar()
        or 0
    )

    if stats.active_users > 0:
        stats.average_posts_per_user = round(stats.post_count / stats.active_users, 2)
        stats.engagement_rate = round(
            (stats.comment_count + stats.total_reactions) / stats.member_count * 100, 2
        )
    else:
        stats.average_posts_per_user = 0
        stats.engagement_rate = 0

    db.commit()
    return stats


# =====================================================
# ==================== Community Endpoints ============
# =====================================================


@router.post(
    "/",
    status_code=status.HTTP_201_CREATED,
    response_model=schemas.CommunityOut,
    summary="Create a new community",
    description="Create a new community with the ability to specify category and tags.",
)
async def create_community(
    community: schemas.CommunityCreate,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(oauth2.get_current_user),
):
    """
    Create a new community with permission checks and basic settings.
    """
    if not current_user.is_verified:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Your account must be verified to create a community",
        )

    owned_communities = (
        db.query(models.Community)
        .filter(models.Community.owner_id == current_user.id)
        .count()
    )
    if owned_communities >= settings.MAX_OWNED_COMMUNITIES:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"You cannot create more than {settings.MAX_OWNED_COMMUNITIES} communities",
        )

    new_community = models.Community(
        owner_id=current_user.id, **community.dict(exclude={"tags", "rules"})
    )

    # Add the creator as a member (Owner)
    member = models.CommunityMember(
        user_id=current_user.id,
        role=models.CommunityRole.OWNER,
        joined_at=datetime.now(timezone.utc),
    )
    new_community.members.append(member)

    if community.category_id:
        category = (
            db.query(models.Category)
            .filter(models.Category.id == community.category_id)
            .first()
        )
        if not category:
            raise HTTPException(status_code=404, detail="Selected category not found")
        new_community.category = category

    if community.tags:
        tags = db.query(models.Tag).filter(models.Tag.id.in_(community.tags)).all()
        new_community.tags.extend(tags)

    if community.rules:
        for rule in community.rules:
            new_rule = models.CommunityRule(
                content=rule.content,
                description=rule.description,
                priority=rule.priority,
            )
            new_community.rules.append(new_rule)

    db.add(new_community)
    db.commit()
    db.refresh(new_community)

    log_user_event(
        db, current_user.id, "create_community", {"community_id": new_community.id}
    )

    create_notification(
        db,
        current_user.id,
        f"A new community has been created: {new_community.name}",
        f"/community/{new_community.id}",
        "new_community",
        new_community.id,
    )

    return schemas.CommunityOut.from_orm(new_community)


@router.get(
    "/",
    response_model=List[schemas.CommunityOut],
    summary="Get list of communities",
    description="Search and filter communities with sorting options.",
)
async def get_communities(
    db: Session = Depends(get_db),
    current_user: models.User = Depends(oauth2.get_current_user),
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
    query = db.query(models.Community)

    if search:
        query = query.filter(
            or_(
                models.Community.name.ilike(f"%{search}%"),
                models.Community.description.ilike(f"%{search}%"),
            )
        )

    if category_id:
        query = query.filter(models.Community.category_id == category_id)

    if sort_by == "created_at":
        query = query.order_by(
            desc(models.Community.created_at)
            if sort_order == "desc"
            else asc(models.Community.created_at)
        )
    elif sort_by == "members_count":
        query = query.order_by(
            desc(models.Community.members_count)
            if sort_order == "desc"
            else asc(models.Community.members_count)
        )
    elif sort_by == "activity":
        query = query.order_by(
            desc(models.Community.last_activity_at)
            if sort_order == "desc"
            else asc(models.Community.last_activity_at)
        )

    communities = query.offset(skip).limit(limit).all()

    for community in communities:
        community.name = await get_translated_content(
            community.name, current_user, community.language
        )
        community.description = await get_translated_content(
            community.description, current_user, community.language
        )

    return [schemas.CommunityOut.from_orm(community) for community in communities]


@router.get(
    "/{id}",
    response_model=schemas.CommunityOut,
    summary="Get specific community details",
)
async def get_community(
    id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(oauth2.get_current_user),
):
    """
    Retrieve detailed information of a specific community along with its related data.
    """
    community = (
        db.query(models.Community)
        .options(
            joinedload(models.Community.members),
            joinedload(models.Community.rules),
            joinedload(models.Community.tags),
            joinedload(models.Community.category),
        )
        .filter(models.Community.id == id)
        .first()
    )

    if not community:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Community not found"
        )

    community.name = await get_translated_content(
        community.name, current_user, community.language
    )
    community.description = await get_translated_content(
        community.description, current_user, community.language
    )

    return schemas.CommunityOut.from_orm(community)


@router.put(
    "/{id}",
    response_model=schemas.CommunityOut,
    summary="Update community information",
)
async def update_community(
    id: int,
    updated_community: schemas.CommunityUpdate,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(oauth2.get_current_user),
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
    community = db.query(models.Community).filter(models.Community.id == id).first()
    if not community:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Community not found"
        )

    from ..routers.community import check_community_permissions

    check_community_permissions(current_user, community, models.CommunityRole.OWNER)

    update_data = updated_community.dict(exclude_unset=True)

    if "category_id" in update_data:
        category = (
            db.query(models.Category)
            .filter(models.Category.id == update_data["category_id"])
            .first()
        )
        if not category:
            raise HTTPException(status_code=404, detail="Selected category not found")
        community.category = category
        del update_data["category_id"]

    if "tags" in update_data:
        community.tags.clear()
        tags = db.query(models.Tag).filter(models.Tag.id.in_(update_data["tags"])).all()
        community.tags.extend(tags)
        del update_data["tags"]

    if "rules" in update_data:
        community.rules.clear()
        for rule_data in update_data["rules"]:
            rule = models.CommunityRule(**rule_data.dict())
            community.rules.append(rule)
        del update_data["rules"]

    for key, value in update_data.items():
        setattr(community, key, value)

    community.updated_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(community)

    create_notification(
        db,
        current_user.id,
        f"Community {community.name} information has been updated",
        f"/community/{community.id}",
        "update_community",
        community.id,
    )

    return schemas.CommunityOut.from_orm(community)


@router.post(
    "/{id}/join",
    status_code=status.HTTP_200_OK,
    summary="Join a community",
)
async def join_community(
    id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(oauth2.get_current_user),
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
    community = db.query(models.Community).filter(models.Community.id == id).first()

    if not community:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Community not found"
        )

    if any(member.user_id == current_user.id for member in community.members):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="You are already a member of this community",
        )

    if community.is_private:
        invitation = (
            db.query(models.CommunityInvitation)
            .filter(
                models.CommunityInvitation.community_id == id,
                models.CommunityInvitation.invitee_id == current_user.id,
                models.CommunityInvitation.status == "pending",
            )
            .first()
        )
        if not invitation:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="This is a private community and requires an invitation to join",
            )

    new_member = models.CommunityMember(
        community_id=id,
        user_id=current_user.id,
        role=models.CommunityRole.MEMBER,
        joined_at=datetime.now(timezone.utc),
    )

    db.add(new_member)
    community.members_count += 1

    if community.is_private and invitation:
        invitation.status = "accepted"
        invitation.accepted_at = datetime.now(timezone.utc)

    db.commit()

    create_notification(
        db,
        community.owner_id,
        f"{current_user.username} has joined the community {community.name}",
        f"/community/{id}",
        "new_member",
        current_user.id,
    )

    return {"message": "Successfully joined the community"}


@router.post(
    "/{community_id}/post",
    status_code=status.HTTP_201_CREATED,
    response_model=schemas.PostOut,
    summary="Create a new post in the community",
)
async def create_community_post(
    community_id: int,
    post: schemas.PostCreate,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(oauth2.get_current_user),
):
    """
    Create a new post in the community with content validation and permission checks.

    Process:
      - Verify community existence.
      - Check if the user is a member.
      - Validate that the post content is not empty.
      - Check for profanity and community rule violations.
      - Create the post and update member and community statistics.
      - Send notifications to community administrators.

    Returns:
      The created post.
    """
    community = (
        db.query(models.Community).filter(models.Community.id == community_id).first()
    )
    if not community:
        raise HTTPException(status_code=404, detail="Community not found")

    member = next((m for m in community.members if m.user_id == current_user.id), None)
    if not member:
        raise HTTPException(
            status_code=403,
            detail="You must be a member of the community to create a post",
        )

    if not post.content.strip():
        raise HTTPException(status_code=400, detail="Post content cannot be empty")

    if check_for_profanity(post.content):
        raise HTTPException(
            status_code=400, detail="Content contains inappropriate language"
        )

    if community.rules:
        if not check_content_against_rules(
            post.content, [rule.content for rule in community.rules]
        ):
            raise HTTPException(
                status_code=400, detail="Content violates community rules"
            )

    new_post = models.Post(
        owner_id=current_user.id,
        community_id=community_id,
        content=post.content,
        language=detect_language(post.content),
        has_media=bool(post.media_urls),
        media_urls=post.media_urls,
    )

    db.add(new_post)
    db.commit()
    db.refresh(new_post)

    community.posts_count += 1
    community.last_activity_at = datetime.now(timezone.utc)
    member.posts_count += 1
    member.last_active_at = datetime.now(timezone.utc)

    if (
        member.posts_count >= ACTIVITY_THRESHOLD_VIP
        and member.role == models.CommunityRole.MEMBER
    ):
        member.role = models.CommunityRole.VIP
        create_notification(
            db,
            current_user.id,
            f"You have been upgraded to VIP in community {community.name}",
            f"/community/{community_id}",
            "role_upgrade",
            None,
        )

    db.commit()

    for admin in community.members:
        if admin.role in [models.CommunityRole.ADMIN, models.CommunityRole.OWNER]:
            create_notification(
                db,
                admin.user_id,
                f"New post by {current_user.username} in community {community.name}",
                f"/post/{new_post.id}",
                "new_post",
                new_post.id,
            )

    return schemas.PostOut.from_orm(new_post)


@router.post(
    "/{community_id}/rules",
    response_model=schemas.CommunityRuleOut,
    summary="Add a new rule to the community",
)
async def add_community_rule(
    community_id: int,
    rule: schemas.CommunityRuleCreate,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(oauth2.get_current_user),
):
    """
    Add a new rule to the community with proper permission checks.
    """
    community = (
        db.query(models.Community).filter(models.Community.id == community_id).first()
    )

    check_community_permissions(current_user, community, models.CommunityRole.ADMIN)

    existing_rules_count = (
        db.query(models.CommunityRule)
        .filter(models.CommunityRule.community_id == community_id)
        .count()
    )
    if existing_rules_count >= MAX_RULES:
        raise HTTPException(
            status_code=400,
            detail=f"Cannot add more than {MAX_RULES} rules to the community",
        )

    new_rule = models.CommunityRule(
        community_id=community_id,
        content=rule.content,
        description=rule.description,
        priority=rule.priority,
        created_by=current_user.id,
        created_at=datetime.now(timezone.utc),
    )
    db.add(new_rule)
    db.commit()
    db.refresh(new_rule)

    for member in community.members:
        create_notification(
            db,
            member.user_id,
            f"A new rule has been added in community {community.name}",
            f"/community/{community_id}/rules",
            "new_rule",
            new_rule.id,
        )

    return schemas.CommunityRuleOut.from_orm(new_rule)


@router.get(
    "/{community_id}/analytics",
    response_model=schemas.CommunityAnalytics,
    summary="Comprehensive community analytics",
)
async def get_community_analytics(
    community_id: int,
    start_date: date,
    end_date: date,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(oauth2.get_current_user),
):
    """
    Retrieve detailed analytics for the community.
    """
    community = (
        db.query(models.Community).filter(models.Community.id == community_id).first()
    )

    check_community_permissions(current_user, community, models.CommunityRole.MODERATOR)

    total_members = (
        db.query(models.CommunityMember)
        .filter(models.CommunityMember.community_id == community_id)
        .count()
    )

    activity_data = (
        db.query(
            func.date(models.Post.created_at).label("date"),
            func.count(models.Post.id).label("posts"),
            func.count(models.Comment.id).label("comments"),
            func.count(func.distinct(models.Post.owner_id)).label("active_users"),
        )
        .outerjoin(models.Comment)
        .filter(
            models.Post.community_id == community_id,
            models.Post.created_at.between(start_date, end_date),
        )
        .group_by(func.date(models.Post.created_at))
        .all()
    )

    engagement_data = (
        db.query(
            func.avg(models.Post.likes_count).label("avg_likes"),
            func.avg(models.Post.comments_count).label("avg_comments"),
            func.sum(models.Post.shares_count).label("total_shares"),
        )
        .filter(
            models.Post.community_id == community_id,
            models.Post.created_at.between(start_date, end_date),
        )
        .first()
    )

    content_analysis = (
        db.query(
            models.Post.content_type,
            func.count(models.Post.id).label("count"),
            func.avg(models.Post.likes_count).label("avg_engagement"),
        )
        .filter(
            models.Post.community_id == community_id,
            models.Post.created_at.between(start_date, end_date),
        )
        .group_by(models.Post.content_type)
        .all()
    )

    growth_data = []
    current_date = start_date
    while current_date <= end_date:
        members_count = (
            db.query(models.CommunityMember)
            .filter(
                models.CommunityMember.community_id == community_id,
                models.CommunityMember.joined_at <= current_date,
            )
            .count()
        )
        growth_data.append({"date": current_date, "members": members_count})
        current_date += timedelta(days=1)

    return {
        "overview": {
            "total_members": total_members,
            "active_members": len(set(d.active_users for d in activity_data)),
            "total_posts": sum(d.posts for d in activity_data),
            "total_comments": sum(d.comments for d in activity_data),
        },
        "activity": [
            {
                "date": d.date.strftime("%Y-%m-%d"),
                "posts": d.posts,
                "comments": d.comments,
                "active_users": d.active_users,
            }
            for d in activity_data
        ],
        "engagement": {
            "avg_likes_per_post": round(engagement_data.avg_likes or 0, 2),
            "avg_comments_per_post": round(engagement_data.avg_comments or 0, 2),
            "total_shares": engagement_data.total_shares or 0,
        },
        "content_analysis": [
            {
                "type": c.content_type,
                "count": c.count,
                "avg_engagement": round(c.avg_engagement or 0, 2),
            }
            for c in content_analysis
        ],
        "growth": growth_data,
    }


@router.put(
    "/{community_id}/members/{user_id}/role",
    response_model=schemas.CommunityMemberOut,
    summary="Update a member's role in the community",
)
async def update_member_role(
    community_id: int,
    user_id: int,
    role_update: schemas.CommunityMemberRoleUpdate,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(oauth2.get_current_user),
):
    """
    Update a member's role in the community after verifying permissions.

    Parameters:
      - community_id: ID of the community.
      - user_id: ID of the member to update.
      - role_update: CommunityMemberRoleUpdate schema with the new role.
      - db: Database session.
      - current_user: The current authenticated user.

    Returns:
      The updated community member information.
    """
    community = (
        db.query(models.Community).filter(models.Community.id == community_id).first()
    )

    check_community_permissions(current_user, community, models.CommunityRole.ADMIN)

    member = (
        db.query(models.CommunityMember)
        .filter(
            models.CommunityMember.community_id == community_id,
            models.CommunityMember.user_id == user_id,
        )
        .first()
    )

    if not member:
        raise HTTPException(status_code=404, detail="Member not found in community")

    if member.role == models.CommunityRole.OWNER:
        raise HTTPException(
            status_code=403, detail="Cannot change the role of the community owner"
        )

    if role_update.role == models.CommunityRole.OWNER:
        raise HTTPException(
            status_code=400, detail="Cannot assign owner role to a member"
        )

    old_role = member.role

    member.role = role_update.role
    member.role_updated_at = datetime.now(timezone.utc)
    member.role_updated_by = current_user.id

    db.commit()
    db.refresh(member)

    create_notification(
        db,
        user_id,
        f"Your role in community {community.name} has been changed from {old_role} to {role_update.role}",
        f"/community/{community_id}",
        "role_update",
        None,
    )

    return schemas.CommunityMemberOut.from_orm(member)


@router.post(
    "/{community_id}/invitations",
    status_code=status.HTTP_201_CREATED,
    response_model=schemas.CommunityInvitationOut,
    summary="Invite new members to the community",
)
async def invite_members(
    community_id: int,
    invitations: List[schemas.CommunityInvitationCreate],
    db: Session = Depends(get_db),
    current_user: models.User = Depends(oauth2.get_current_user),
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
    community = (
        db.query(models.Community).filter(models.Community.id == community_id).first()
    )

    check_community_permissions(current_user, community, models.CommunityRole.MEMBER)

    active_invitations = (
        db.query(models.CommunityInvitation)
        .filter(
            models.CommunityInvitation.community_id == community_id,
            models.CommunityInvitation.inviter_id == current_user.id,
            models.CommunityInvitation.status == "pending",
        )
        .count()
    )

    if active_invitations + len(invitations) > settings.MAX_PENDING_INVITATIONS:
        raise HTTPException(
            status_code=400,
            detail=f"Cannot send more than {settings.MAX_PENDING_INVITATIONS} pending invitations",
        )

    created_invitations = []
    for invitation in invitations:
        invitee = (
            db.query(models.User)
            .filter(models.User.id == invitation.invitee_id)
            .first()
        )
        if not invitee:
            continue

        existing_invitation = (
            db.query(models.CommunityInvitation)
            .filter(
                models.CommunityInvitation.community_id == community_id,
                models.CommunityInvitation.invitee_id == invitation.invitee_id,
                models.CommunityInvitation.status == "pending",
            )
            .first()
        )
        if existing_invitation:
            continue

        is_member = (
            db.query(models.CommunityMember)
            .filter(
                models.CommunityMember.community_id == community_id,
                models.CommunityMember.user_id == invitation.invitee_id,
            )
            .first()
        )
        if is_member:
            continue

        new_invitation = models.CommunityInvitation(
            community_id=community_id,
            inviter_id=current_user.id,
            invitee_id=invitation.invitee_id,
            message=invitation.message,
            expires_at=datetime.now(timezone.utc)
            + timedelta(days=settings.INVITATION_EXPIRY_DAYS),
        )

        db.add(new_invitation)
        created_invitations.append(new_invitation)

        create_notification(
            db,
            invitation.invitee_id,
            f"You have an invitation to join community {community.name} from {current_user.username}",
            f"/invitations/{new_invitation.id}",
            "community_invitation",
            new_invitation.id,
        )

    db.commit()

    for invitation in created_invitations:
        db.refresh(invitation)

    return [schemas.CommunityInvitationOut.from_orm(inv) for inv in created_invitations]


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
    db: Session = Depends(get_db),
    current_user: models.User = Depends(oauth2.get_current_user),
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
    community = (
        db.query(models.Community).filter(models.Community.id == community_id).first()
    )

    check_community_permissions(current_user, community, models.CommunityRole.ADMIN)

    output = StringIO()
    writer = csv.writer(output)

    if data_type == "members":
        writer.writerow(
            [
                "Member ID",
                "Username",
                "Role",
                "Joined Date",
                "Posts Count",
                "Activity Score",
                "Last Active",
            ]
        )

        members = (
            db.query(models.CommunityMember)
            .filter(models.CommunityMember.community_id == community_id)
            .all()
        )
        for member in members:
            writer.writerow(
                [
                    member.user_id,
                    member.user.username,
                    member.role,
                    member.joined_at.strftime("%Y-%m-%d"),
                    member.posts_count,
                    member.activity_score,
                    (
                        member.last_active_at.strftime("%Y-%m-%d %H:%M")
                        if member.last_active_at
                        else "N/A"
                    ),
                ]
            )

    elif data_type == "posts":
        writer.writerow(
            [
                "Post ID",
                "Owner",
                "Posted At",
                "Likes Count",
                "Comments Count",
                "Content Type",
                "Status",
            ]
        )

        query = db.query(models.Post).filter(models.Post.community_id == community_id)
        if date_from:
            query = query.filter(models.Post.created_at >= date_from)
        if date_to:
            query = query.filter(models.Post.created_at <= date_to)
        posts = query.all()
        for post in posts:
            writer.writerow(
                [
                    post.id,
                    post.owner.username,
                    post.created_at.strftime("%Y-%m-%d %H:%M"),
                    post.likes_count,
                    post.comments_count,
                    post.content_type,
                    post.status,
                ]
            )

    elif data_type == "analytics":
        writer.writerow(
            [
                "Date",
                "Member Count",
                "New Posts",
                "Comments",
                "Active Users",
                "Total Reactions",
                "Engagement Rate",
            ]
        )

        stats = get_community_statistics(
            db,
            community_id,
            date_from or (datetime.now() - timedelta(days=30)).date(),
            date_to or datetime.now().date(),
        )
        for stat in stats:
            writer.writerow(
                [
                    stat.date.strftime("%Y-%m-%d"),
                    stat.member_count,
                    stat.post_count,
                    stat.comment_count,
                    stat.active_users,
                    stat.total_reactions,
                    f"{stat.engagement_rate:.2f}%",
                ]
            )

    output.seek(0)
    headers = {
        "Content-Disposition": f"attachment; filename=community_{community_id}_{data_type}_{datetime.now().strftime('%Y%m%d')}.csv"
    }
    return StreamingResponse(
        iter([output.getvalue()]), media_type="text/csv", headers=headers
    )


# ==================== Notification Handling ====================


class CommunityNotificationHandler:
    """
    Community Notification Handler
    Handles notifications related to community events.
    """

    def __init__(self, db: Session, background_tasks: BackgroundTasks):
        self.db = db
        self.background_tasks = background_tasks
        self.notification_service = NotificationService(db, background_tasks)

    async def handle_new_member(self, community: models.Community, member: models.User):
        """
        Handle notifications for a new member joining the community.
        """
        admins = [
            m
            for m in community.members
            if m.role in [models.CommunityRole.ADMIN, models.CommunityRole.OWNER]
        ]
        for admin in admins:
            await self.notification_service.create_notification(
                user_id=admin.user_id,
                content=f"{member.username} has joined community {community.name}",
                notification_type="new_member",
                priority=models.NotificationPriority.LOW,
                category=models.NotificationCategory.COMMUNITY,
                link=f"/community/{community.id}/members",
                metadata={"community_id": community.id, "member_id": member.id},
            )
        await self.notification_service.create_notification(
            user_id=member.id,
            content=f"Welcome to community {community.name}!",
            notification_type="welcome",
            priority=models.NotificationPriority.HIGH,
            category=models.NotificationCategory.COMMUNITY,
            link=f"/community/{community.id}",
            metadata={
                "community_id": community.id,
                "rules_count": len(community.rules),
            },
        )

    async def handle_content_violation(
        self,
        community: models.Community,
        content: Union[models.Post, models.Comment],
        violation_type: str,
        reporter: models.User,
    ):
        """
        Handle notifications for content violation.
        """
        admins = [
            m
            for m in community.members
            if m.role in [models.CommunityRole.ADMIN, models.CommunityRole.MODERATOR]
        ]
        content_type = "post" if isinstance(content, models.Post) else "comment"
        for admin in admins:
            await self.notification_service.create_notification(
                user_id=admin.user_id,
                content=f"{content_type.capitalize()} in community {community.name} has been flagged. Violation: {violation_type}",
                notification_type="content_violation",
                priority=models.NotificationPriority.HIGH,
                category=models.NotificationCategory.MODERATION,
                link=f"/moderation/content/{content.id}",
                metadata={
                    "community_id": community.id,
                    "content_id": content.id,
                    "content_type": content_type,
                    "violation_type": violation_type,
                    "reporter_id": reporter.id,
                },
            )

    async def handle_role_change(
        self,
        community: models.Community,
        member: models.CommunityMember,
        old_role: str,
        changed_by: models.User,
    ):
        """
        Handle notifications for a role change within the community.
        """
        await self.notification_service.create_notification(
            user_id=member.user_id,
            content=f"Your role in community {community.name} has been changed from {old_role} to {member.role}",
            notification_type="role_change",
            priority=models.NotificationPriority.HIGH,
            category=models.NotificationCategory.COMMUNITY,
            link=f"/community/{community.id}",
            metadata={
                "community_id": community.id,
                "old_role": old_role,
                "new_role": member.role,
                "changed_by": changed_by.id,
            },
        )

    async def handle_community_achievement(
        self, community: models.Community, achievement_type: str, achievement_data: dict
    ):
        """
        Handle notifications for community achievements.
        """
        for member in community.members:
            await self.notification_service.create_notification(
                user_id=member.user_id,
                content=self._get_achievement_message(
                    achievement_type, achievement_data, community.name
                ),
                notification_type="community_achievement",
                priority=models.NotificationPriority.MEDIUM,
                category=models.NotificationCategory.ACHIEVEMENT,
                link=f"/community/{community.id}/achievements",
                metadata={
                    "community_id": community.id,
                    "achievement_type": achievement_type,
                    **achievement_data,
                },
            )

    def _get_achievement_message(
        self, achievement_type: str, data: dict, community_name: str
    ) -> str:
        """
        Get an appropriate achievement message.
        """
        messages = {
            "members_milestone": f"Community {community_name} has reached {data['count']} members! 🎉",
            "posts_milestone": f"{data['count']} posts have been published in community {community_name}! 🎉",
            "engagement_milestone": f"Engagement rate in community {community_name} has reached {data['rate']}%! 🎉",
            "active_streak": f"Community {community_name} has been active for {data['days']} consecutive days! 🔥",
        }
        return messages.get(
            achievement_type, f"New achievement in community {community_name}!"
        )


# ==================== Periodic Tasks ====================


async def cleanup_expired_invitations(db: Session):
    """
    Clean up expired community invitations.
    """
    expired_invitations = (
        db.query(models.CommunityInvitation)
        .filter(
            models.CommunityInvitation.status == "pending",
            models.CommunityInvitation.expires_at <= datetime.now(timezone.utc),
        )
        .all()
    )
    for invitation in expired_invitations:
        invitation.status = "expired"
        create_notification(
            db,
            invitation.invitee_id,
            f"Your invitation to join community {invitation.community.name} has expired",
            f"/community/{invitation.community_id}",
            "invitation_expired",
            invitation.id,
        )
    db.commit()


async def update_community_rankings(db: Session):
    """
    Update community rankings based on various metrics.
    """
    communities = db.query(models.Community).all()
    for community in communities:
        activity_score = (
            community.posts_count * 2
            + community.comment_count * 1
            + community.members_count * 3
            + community.total_reactions
        )
        growth_rate = await calculate_community_growth_rate(db, community.id)
        community.activity_score = activity_score
        community.growth_rate = growth_rate
        community.ranking = await calculate_community_ranking(
            activity_score, growth_rate, community.age_in_days
        )
    db.commit()


async def calculate_community_ranking(
    activity_score: float, growth_rate: float, age_in_days: int
) -> float:
    """
    Calculate community ranking based on multiple factors.
    """
    age_factor = min(1.0, age_in_days / 365)
    ranking = (activity_score * 0.4) + (growth_rate * 0.4) + (age_factor * 0.2)
    return round(ranking, 2)


async def calculate_community_growth_rate(db: Session, community_id: int) -> float:
    """
    Calculate the growth rate of the community.
    """
    now = datetime.now(timezone.utc)
    current_month_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    previous_month_start = (current_month_start - timedelta(days=1)).replace(day=1)

    current_stats = await get_community_monthly_stats(
        db, community_id, current_month_start
    )
    previous_stats = await get_community_monthly_stats(
        db, community_id, previous_month_start
    )

    if previous_stats["members"] == 0:
        return 100 if current_stats["members"] > 0 else 0

    growth_rates = {
        "members": (
            (current_stats["members"] - previous_stats["members"])
            / previous_stats["members"]
        )
        * 100,
        "posts": (
            (current_stats["posts"] - previous_stats["posts"]) / previous_stats["posts"]
        )
        * 100,
        "engagement": (
            (current_stats["engagement"] - previous_stats["engagement"])
            / previous_stats["engagement"]
        )
        * 100,
    }

    weighted_growth = (
        (growth_rates["members"] * 0.4)
        + (growth_rates["posts"] * 0.3)
        + (growth_rates["engagement"] * 0.3)
    )
    return round(weighted_growth, 2)
