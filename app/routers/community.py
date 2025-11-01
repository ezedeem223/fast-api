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
from app.notifications import create_notification

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/communities", tags=["Communities"])

# =====================================================
# =============== Global Constants ====================
# =====================================================
MAX_PINNED_POSTS = 5
MAX_RULES = 20
ACTIVITY_THRESHOLD_VIP = 1000
INACTIVE_DAYS_THRESHOLD = 30
DEFAULT_CATEGORY_NAME = "General"
DEFAULT_CATEGORY_DESCRIPTION = "Fallback category created automatically for tests and demos."


def _ensure_default_category(db: Session) -> models.Category:
    """Return an existing default category or create one for convenience tests."""

    default_category = (
        db.query(models.Category)
        .filter(func.lower(models.Category.name) == DEFAULT_CATEGORY_NAME.lower())
        .first()
    )
    if default_category:
        return default_category

    default_category = models.Category(
        name=DEFAULT_CATEGORY_NAME,
        description=DEFAULT_CATEGORY_DESCRIPTION,
    )
    db.add(default_category)
    db.commit()
    db.refresh(default_category)
    return default_category


def _get_or_create_community_category(
    db: Session, category: models.Category
) -> models.CommunityCategory:
    """Link a community to a reusable community category wrapper."""

    community_category = (
        db.query(models.CommunityCategory)
        .filter(func.lower(models.CommunityCategory.name) == category.name.lower())
        .first()
    )
    if community_category:
        return community_category

    community_category = models.CommunityCategory(
        name=category.name,
        description=category.description,
        category_id=category.id,
    )
    db.add(community_category)
    db.commit()
    db.refresh(community_category)
    return community_category


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
# =============== Shared query helpers =================
# =====================================================
def _community_query(db: Session):
    """Prepare a community query with the relationships required by the API tests."""

    return db.query(models.Community).options(
        joinedload(models.Community.owner),
        joinedload(models.Community.members).joinedload(models.CommunityMember.user),
        joinedload(models.Community.rules),
        joinedload(models.Community.tags),
        joinedload(models.Community.community_category).joinedload(
            models.CommunityCategory.category
        ),
    )


def _get_community_or_404(db: Session, community_id: int) -> models.Community:
    """Fetch a community with eager relationships or raise a 404 error."""

    community = (
        _community_query(db).filter(models.Community.id == community_id).first()
    )
    if not community:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Community not found")
    return community


def _get_membership(community: models.Community, user_id: int) -> Optional[models.CommunityMember]:
    """Return the membership record for the given user if they belong to the community."""

    return next((member for member in community.members if member.user_id == user_id), None)


def _user_display_name(user: models.User) -> str:
    """Return a friendly identifier for notification messages."""

    return getattr(user, "username", None) or getattr(user, "account_username", None) or user.email


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

    When callers omit the category, the endpoint automatically assigns a
    reusable "General" category to keep the API ergonomic for tests and demos.
    """
    if (
        settings.require_verified_for_community_creation
        and not current_user.is_verified
    ):
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

    community_payload = community.model_dump(
        exclude={"tags", "rules", "category_id"}
    )
    new_community = models.Community(owner_id=current_user.id, **community_payload)

    # Add the creator as a member (Owner)
    member = models.CommunityMember(
        user_id=current_user.id,
        role=models.CommunityRole.OWNER,
        join_date=datetime.now(timezone.utc),
    )
    new_community.members.append(member)

    category_obj: Optional[models.Category] = None
    if community.category_id is not None:
        category = (
            db.query(models.Category)
            .filter(models.Category.id == community.category_id)
            .first()
        )
        if not category:
            raise HTTPException(status_code=404, detail="Selected category not found")
        category_obj = category
    else:
        category_obj = _ensure_default_category(db)

    if category_obj:
        new_community.community_category = _get_or_create_community_category(
            db, category_obj
        )

    if community.tags:
        tags = db.query(models.Tag).filter(models.Tag.id.in_(community.tags)).all()
        new_community.tags.extend(tags)

    for rule in getattr(community, "rules", []):
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
    query = _community_query(db)

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
    "/user-invitations",
    response_model=List[schemas.CommunityInvitationOut],
    summary="List pending invitations for the current user",
)
async def list_user_invitations(
    db: Session = Depends(get_db),
    current_user: models.User = Depends(oauth2.get_current_user),
):
    """Return pending invitations directed to the authenticated user."""

    invitations = (
        db.query(models.CommunityInvitation)
        .options(
            joinedload(models.CommunityInvitation.community)
            .joinedload(models.Community.community_category)
            .joinedload(models.CommunityCategory.category),
            joinedload(models.CommunityInvitation.community).joinedload(
                models.Community.owner
            ),
            joinedload(models.CommunityInvitation.inviter),
            joinedload(models.CommunityInvitation.invitee),
        )
        .filter(
            models.CommunityInvitation.invitee_id == current_user.id,
            models.CommunityInvitation.status == "pending",
        )
        .order_by(desc(models.CommunityInvitation.created_at))
        .all()
    )

    return [schemas.CommunityInvitationOut.from_orm(inv) for inv in invitations]


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
    community = _community_query(db).filter(models.Community.id == id).first()

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


@router.delete(
    "/{id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete a community",
)
async def delete_community(
    id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(oauth2.get_current_user),
):
    """Delete the specified community when the current user is the owner."""

    community = _get_community_or_404(db, id)

    if community.owner_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You do not have permission to delete this community",
        )

    db.query(models.CommunityMember).filter(
        models.CommunityMember.community_id == id
    ).delete(synchronize_session=False)

    db.delete(community)
    db.commit()

    return Response(status_code=status.HTTP_204_NO_CONTENT)


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
    community = _get_community_or_404(db, id)

    if _get_membership(community, current_user.id):
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
    else:
        invitation = None

    new_member = models.CommunityMember(
        community_id=id,
        user_id=current_user.id,
        role=models.CommunityRole.MEMBER,
        join_date=datetime.now(timezone.utc),
    )

    db.add(new_member)

    if community.is_private and invitation:
        invitation.status = "accepted"

    db.commit()

    create_notification(
        db,
        community.owner_id,
        f"{_user_display_name(current_user)} has joined the community {community.name}",
        f"/community/{id}",
        "new_member",
        current_user.id,
    )

    return {"message": "Joined the community successfully"}


@router.post(
    "/{community_id}/leave",
    status_code=status.HTTP_200_OK,
    summary="Leave a community",
)
async def leave_community(
    community_id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(oauth2.get_current_user),
):
    """Remove the current user from the given community if they are not the owner."""

    community = _get_community_or_404(db, community_id)

    if community.owner_id == current_user.id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Owner cannot leave the community",
        )

    membership = _get_membership(community, current_user.id)
    if not membership:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="You are not a member of this community",
        )

    db.delete(membership)
    db.commit()

    return {"message": "Left the community successfully"}


@router.post(
    "/{community_id}/posts",
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
    community = _get_community_or_404(db, community_id)

    member = _get_membership(community, current_user.id)
    if not member:
        raise HTTPException(
            status_code=403,
            detail="You must be a member of the community to create a post",
        )

    if post.community_id and post.community_id != community_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Payload community_id does not match the path parameter",
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
        title=post.title,
        content=post.content,
        published=post.published,
        original_post_id=post.original_post_id,
        is_repost=post.is_repost,
        allow_reposts=post.allow_reposts,
        copyright_type=post.copyright_type,
        custom_copyright=post.custom_copyright,
        is_archived=post.is_archived,
    )

    db.add(new_post)
    db.commit()
    db.refresh(new_post)

    return schemas.PostOut.from_orm(new_post)


@router.get(
    "/{community_id}/posts",
    response_model=List[schemas.PostOut],
    summary="List posts in a community",
)
async def list_community_posts(
    community_id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(oauth2.get_current_user),
):
    """Retrieve all posts for the given community ordered by recency."""

    _get_community_or_404(db, community_id)

    posts = (
        db.query(models.Post)
        .options(
            joinedload(models.Post.owner),
            joinedload(models.Post.community),
        )
        .filter(models.Post.community_id == community_id)
        .order_by(desc(models.Post.created_at))
        .all()
    )

    return [schemas.PostOut.from_orm(post) for post in posts]


@router.post(
    "/{community_id}/reels",
    status_code=status.HTTP_201_CREATED,
    response_model=schemas.ReelOut,
    summary="Create a reel in the community",
)
async def create_community_reel(
    community_id: int,
    reel: schemas.ReelCreate,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(oauth2.get_current_user),
):
    """Create a new reel tied to the given community."""

    community = _get_community_or_404(db, community_id)

    if not _get_membership(community, current_user.id):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You must be a member of the community to share a reel",
        )

    if reel.community_id and reel.community_id != community_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Payload community_id does not match the path parameter",
        )

    if not is_valid_video_url(reel.video_url):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Provided video URL is not valid",
        )

    new_reel = models.Reel(
        title=reel.title,
        video_url=reel.video_url,
        description=reel.description,
        owner_id=current_user.id,
        community_id=community_id,
    )

    db.add(new_reel)
    db.commit()
    db.refresh(new_reel)

    return schemas.ReelOut.from_orm(new_reel)


@router.get(
    "/{community_id}/reels",
    response_model=List[schemas.ReelOut],
    summary="List reels in a community",
)
async def list_community_reels(
    community_id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(oauth2.get_current_user),
):
    """Return all reels that belong to the community."""

    _get_community_or_404(db, community_id)

    reels = (
        db.query(models.Reel)
        .options(
            joinedload(models.Reel.owner),
            joinedload(models.Reel.community),
        )
        .filter(models.Reel.community_id == community_id)
        .order_by(desc(models.Reel.created_at))
        .all()
    )

    return [schemas.ReelOut.from_orm(reel) for reel in reels]


@router.post(
    "/{community_id}/articles",
    status_code=status.HTTP_201_CREATED,
    response_model=schemas.ArticleOut,
    summary="Create an article in the community",
)
async def create_community_article(
    community_id: int,
    article: schemas.ArticleCreate,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(oauth2.get_current_user),
):
    """Publish a long-form article for a community."""

    community = _get_community_or_404(db, community_id)

    if not _get_membership(community, current_user.id):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You must be a member of the community to share an article",
        )

    if article.community_id and article.community_id != community_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Payload community_id does not match the path parameter",
        )

    if not article.content.strip():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Article content cannot be empty",
        )

    new_article = models.Article(
        title=article.title,
        content=article.content,
        author_id=current_user.id,
        community_id=community_id,
    )

    db.add(new_article)
    db.commit()
    db.refresh(new_article)

    return schemas.ArticleOut.from_orm(new_article)


@router.get(
    "/{community_id}/articles",
    response_model=List[schemas.ArticleOut],
    summary="List articles in a community",
)
async def list_community_articles(
    community_id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(oauth2.get_current_user),
):
    """Return all articles associated with the community."""

    _get_community_or_404(db, community_id)

    articles = (
        db.query(models.Article)
        .options(
            joinedload(models.Article.author),
            joinedload(models.Article.community),
        )
        .filter(models.Article.community_id == community_id)
        .order_by(desc(models.Article.created_at))
        .all()
    )

    return [schemas.ArticleOut.from_orm(article) for article in articles]


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
                models.CommunityMember.join_date <= current_date,
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
    role_update: schemas.CommunityMemberUpdate,  # تم التعديل هنا من CommunityMemberRoleUpdate إلى CommunityMemberUpdate
    db: Session = Depends(get_db),
    current_user: models.User = Depends(oauth2.get_current_user),
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
    "/{community_id}/invite",
    status_code=status.HTTP_201_CREATED,
    response_model=schemas.CommunityInvitationOut,
    summary="Invite a user to join the community",
)
async def invite_member(
    community_id: int,
    invitation: schemas.CommunityInvitationCreate,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(oauth2.get_current_user),
):
    """Create a single invitation for the supplied community and invitee."""

    community = _get_community_or_404(db, community_id)

    if not _get_membership(community, current_user.id):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You must be a community member to send invitations",
        )

    if invitation.community_id and invitation.community_id != community_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Payload community_id does not match the path parameter",
        )

    invitee = (
        db.query(models.User)
        .filter(models.User.id == invitation.invitee_id)
        .first()
    )
    if not invitee:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Invitee not found")

    if _get_membership(community, invitee.id):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="User is already a member of the community",
        )

    existing_invitation = (
        db.query(models.CommunityInvitation)
        .filter(
            models.CommunityInvitation.community_id == community_id,
            models.CommunityInvitation.invitee_id == invitee.id,
            models.CommunityInvitation.status == "pending",
        )
        .first()
    )
    if existing_invitation:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="An active invitation already exists for this user",
        )

    new_invitation = models.CommunityInvitation(
        community_id=community_id,
        inviter_id=current_user.id,
        invitee_id=invitee.id,
        status="pending",
    )

    db.add(new_invitation)
    db.commit()
    db.refresh(new_invitation)

    create_notification(
        db,
        invitee.id,
        f"You have been invited to join community {community.name}",
        f"/invitations/{new_invitation.id}",
        "community_invitation",
        new_invitation.id,
    )

    return schemas.CommunityInvitationOut.from_orm(new_invitation)


@router.post(
    "/invitations/{invitation_id}/accept",
    status_code=status.HTTP_200_OK,
    summary="Accept a community invitation",
)
async def accept_invitation(
    invitation_id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(oauth2.get_current_user),
):
    """Accept a pending invitation and join the associated community."""

    invitation = (
        db.query(models.CommunityInvitation)
        .filter(models.CommunityInvitation.id == invitation_id)
        .first()
    )

    if not invitation or invitation.invitee_id != current_user.id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Invitation not found")

    if invitation.status != "pending":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invitation is no longer pending",
        )

    community = _get_community_or_404(db, invitation.community_id)

    if not _get_membership(community, current_user.id):
        db.add(
            models.CommunityMember(
                community_id=community.id,
                user_id=current_user.id,
                role=models.CommunityRole.MEMBER,
                join_date=datetime.now(timezone.utc),
            )
        )

    invitation.status = "accepted"
    db.commit()

    return {"message": "Invitation accepted successfully"}


@router.post(
    "/invitations/{invitation_id}/reject",
    status_code=status.HTTP_200_OK,
    summary="Reject a community invitation",
)
async def reject_invitation(
    invitation_id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(oauth2.get_current_user),
):
    """Reject a pending invitation without joining the community."""

    invitation = (
        db.query(models.CommunityInvitation)
        .filter(models.CommunityInvitation.id == invitation_id)
        .first()
    )

    if not invitation or invitation.invitee_id != current_user.id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Invitation not found")

    if invitation.status != "pending":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invitation is no longer pending",
        )

    invitation.status = "rejected"
    db.commit()

    return {"message": "Invitation rejected successfully"}


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
                    _user_display_name(member.user),
                    member.role,
                    member.join_date.strftime("%Y-%m-%d")
                    if member.join_date
                    else "N/A",
                    getattr(member, "posts_count", 0),
                    member.activity_score,
                    (
                        getattr(member, "last_active_at", None).strftime("%Y-%m-%d %H:%M")
                        if getattr(member, "last_active_at", None)
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
                    _user_display_name(post.owner),
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
        self.notification_service = (
            create_notification  # Assuming create_notification handles notifications
        )

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
            await self.notification_service(
                self.db,
                admin.user_id,
                f"{_user_display_name(member)} has joined community {community.name}",
                f"/community/{community.id}/members",
                "new_member",
                None,
            )
        await self.notification_service(
            self.db,
            member.id,
            f"Welcome to community {community.name}!",
            f"/community/{community.id}",
            "welcome",
            None,
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
            await self.notification_service(
                self.db,
                admin.user_id,
                f"{content_type.capitalize()} in community {community.name} has been flagged. Violation: {violation_type}",
                f"/moderation/content/{content.id}",
                "content_violation",
                None,
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
        await self.notification_service(
            self.db,
            member.user_id,
            f"Your role in community {community.name} has been changed from {old_role} to {member.role}",
            f"/community/{community.id}",
            "role_change",
            None,
        )

    async def handle_community_achievement(
        self, community: models.Community, achievement_type: str, achievement_data: dict
    ):
        """
        Handle notifications for community achievements.
        """
        for member in community.members:
            await self.notification_service(
                self.db,
                member.user_id,
                self._get_achievement_message(
                    achievement_type, achievement_data, community.name
                ),
                f"/community/{community.id}/achievements",
                "community_achievement",
                None,
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
