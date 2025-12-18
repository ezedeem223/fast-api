"""Community domain business logic for memberships, rules, invitations, and content stats."""

from __future__ import annotations

import csv
from datetime import date, datetime, timedelta, timezone
from io import StringIO
from typing import Dict, List, Optional, Tuple

from fastapi import HTTPException, status
from sqlalchemy import asc, desc, func, or_
from sqlalchemy.orm import Session, joinedload

from app.analytics import analyze_content
from app.modules.community.models import (
    Community,
    CommunityCategory,
    CommunityMember,
    CommunityRole,
    CommunityRule,
    CommunityInvitation,
    CommunityStatistics,
    Category,
    Tag,
)
from app.modules.posts.models import Post, Comment
from app.modules.social import Vote
from app.modules.users.models import PrivacyLevel, User
from app.schemas import (
    CommunityCreate,
    CommunityInvitationCreate,
    CommunityMemberUpdate,
    CommunityUpdate,
    PostCreate,
)
from app.modules.utils.content import (
    check_content_against_rules,
    check_for_profanity,
)
from app.modules.utils.translation import get_translated_content
from app.modules.utils.common import get_user_display_name
from app.modules.utils.events import log_user_event
from app.notifications import create_notification
from app.core.config import settings

MAX_COMMUNITY_RULES = getattr(settings, "MAX_COMMUNITY_RULES", 20)
ACTIVITY_THRESHOLD_VIP = getattr(settings, "COMMUNITY_VIP_THRESHOLD", 1000)


class CommunityService:
    def __init__(self, db: Session):
        self.db = db
        self._translated_fields = ("name", "description")

    def create_community(
        self,
        *,
        current_user: User,
        payload: CommunityCreate,
    ) -> Community:
        if not current_user.is_verified:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Your account must be verified to create a community",
            )

        owned = (
            self.db.query(Community)
            .filter(Community.owner_id == current_user.id)
            .count()
        )
        if owned >= settings.MAX_OWNED_COMMUNITIES:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=(
                    f"You cannot create more than {settings.MAX_OWNED_COMMUNITIES} communities"
                ),
            )

        new_community = Community(
            owner_id=current_user.id,
            **payload.model_dump(exclude={"tags", "rules", "category_id"}),
        )

        owner_member = CommunityMember(
            user_id=current_user.id,
            role=CommunityRole.OWNER,
            join_date=datetime.now(timezone.utc),
        )
        new_community.members.append(owner_member)

        if payload.category_id:
            category = (
                self.db.query(Category)
                .filter(Category.id == payload.category_id)
                .first()
            )
            if not category:
                raise HTTPException(
                    status_code=404, detail="Selected category not found"
                )
            new_community.category = category

        if payload.tags:
            tags = self.db.query(Tag).filter(Tag.id.in_(payload.tags)).all()
            new_community.tags.extend(tags)

        if payload.rules:
            for rule in payload.rules:
                new_rule = CommunityRule(
                    content=rule.content,
                    description=rule.description,
                    priority=rule.priority,
                )
                new_community.rules.append(new_rule)

        self.db.add(new_community)
        self.db.commit()
        self.db.refresh(new_community)

        log_user_event(
            self.db,
            current_user.id,
            "create_community",
            {"community_id": new_community.id},
        )

        create_notification(
            self.db,
            current_user.id,
            f"A new community has been created: {new_community.name}",
            f"/community/{new_community.id}",
            "new_community",
            new_community.id,
        )

        return new_community

    def get_communities(
        self,
        *,
        skip: int = 0,
        limit: int = 20,
        search: Optional[str] = None,
        category: Optional[str] = None,
        is_active: Optional[bool] = None,
        sort_by: str = "created_at",
        order: str = "desc",
    ) -> List[Community]:
        """
        Lightweight community listing used by the router and tests.
        """
        query = self.db.query(Community)

        if search:
            ilike_pattern = f"%{search}%"
            query = query.filter(
                or_(
                    Community.name.ilike(ilike_pattern),
                    Community.description.ilike(ilike_pattern),
                )
            )

        if category:
            query = query.join(CommunityCategory, isouter=True).join(
                Category, Category.id == CommunityCategory.category_id, isouter=True
            )
            query = query.filter(Category.name == category)

        if is_active is not None:
            query = query.filter(Community.is_active.is_(is_active))

        sort_mapping = {
            "created_at": Community.created_at,
            "member_count": Community.member_count,
            "name": Community.name,
        }
        sort_column = sort_mapping.get(sort_by, Community.created_at)
        if order == "asc":
            query = query.order_by(asc(sort_column))
        else:
            query = query.order_by(desc(sort_column))

        return query.offset(skip).limit(limit).all()

    async def list_communities(
        self,
        *,
        current_user: User,
        skip: int,
        limit: int,
        search: str,
        category_id: Optional[int],
        sort_by: str,
        sort_order: str,
    ):
        query = self.db.query(Community)

        if search:
            query = query.filter(
                or_(
                    Community.name.ilike(f"%{search}%"),
                    Community.description.ilike(f"%{search}%"),
                )
            )

        if category_id:
            query = query.filter(Community.category_id == category_id)

        if sort_by == "members_count":
            order_column = Community.members_count
        elif sort_by == "activity":
            order_column = Community.last_activity_at
        else:
            order_column = Community.created_at

        query = query.order_by(
            desc(order_column) if sort_order == "desc" else asc(order_column)
        )

        communities = query.offset(skip).limit(limit).all()

        for community in communities:
            community.name = await get_translated_content(
                community.name, current_user, community.language
            )
            community.description = await get_translated_content(
                community.description, current_user, community.language
            )

        return communities

    async def get_community(
        self, *, community_id: int, current_user: User
    ) -> Community:
        community = (
            self.db.query(Community)
            .options(
                joinedload(Community.members),
                joinedload(Community.rules),
                joinedload(Community.tags),
                joinedload(Community.community_category).joinedload(
                    CommunityCategory.category
                ),
            )
            .filter(Community.id == community_id)
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
        return community

    def update_community(
        self,
        *,
        community_id: int,
        payload: CommunityUpdate,
        current_user: User,
    ) -> Community:
        community = (
            self.db.query(Community).filter(Community.id == community_id).first()
        )
        if not community:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail="Community not found"
            )

        self._ensure_permissions(current_user, community, CommunityRole.OWNER)

        update_data = payload.model_dump(exclude_unset=True)

        if "category_id" in update_data:
            category = (
                self.db.query(Category)
                .filter(Category.id == update_data["category_id"])
                .first()
            )
            if not category:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail="Selected category not found",
                )
            community.category = category
            update_data.pop("category_id")

        if "tags" in update_data:
            community.tags.clear()
            if update_data["tags"]:
                tags = self.db.query(Tag).filter(Tag.id.in_(update_data["tags"])).all()
                community.tags.extend(tags)
            update_data.pop("tags")

        if "rules" in update_data:
            community.rules.clear()
            for rule_data in update_data["rules"]:
                new_rule = CommunityRule(**rule_data.model_dump())
                community.rules.append(new_rule)
            update_data.pop("rules")

        for key, value in update_data.items():
            setattr(community, key, value)

        self.db.commit()
        self.db.refresh(community)

        log_user_event(
            self.db,
            current_user.id,
            "update_community",
            {"community_id": community.id},
        )

        create_notification(
            self.db,
            current_user.id,
            f"Community {community.name} was updated",
            f"/community/{community.id}",
            "community_updated",
            community.id,
        )

        return community

    def update_member_role(
        self,
        *,
        community_id: int,
        user_id: int,
        payload: CommunityMemberUpdate,
        current_user: User,
    ) -> CommunityMember:
        community = (
            self.db.query(Community)
            .options(joinedload(Community.members))
            .filter(Community.id == community_id)
            .first()
        )
        if not community:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail="Community not found"
            )

        self._ensure_permissions(current_user, community, CommunityRole.ADMIN)

        member = (
            self.db.query(CommunityMember)
            .filter(
                CommunityMember.community_id == community_id,
                CommunityMember.user_id == user_id,
            )
            .first()
        )

        if not member:
            raise HTTPException(status_code=404, detail="Member not found in community")

        if member.role == CommunityRole.OWNER:
            raise HTTPException(
                status_code=403, detail="Cannot change the role of the community owner"
            )

        if payload.role == CommunityRole.OWNER:
            raise HTTPException(
                status_code=400, detail="Cannot assign owner role to a member"
            )

        old_role = member.role
        member.role = payload.role
        member.role_updated_at = datetime.now(timezone.utc)
        member.role_updated_by = current_user.id

        self.db.commit()
        self.db.refresh(member)

        create_notification(
            self.db,
            user_id,
            f"Your role in community {community.name} has been changed from {old_role} to {payload.role}",
            f"/community/{community_id}",
            "role_update",
            None,
        )

        return member

    def invite_members(
        self,
        *,
        community_id: int,
        invitations: List[CommunityInvitationCreate],
        current_user: User,
    ) -> List[CommunityInvitation]:
        community = (
            self.db.query(Community).filter(Community.id == community_id).first()
        )
        if not community:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail="Community not found"
            )

        self._ensure_permissions(current_user, community, CommunityRole.MEMBER)

        active_invitations = (
            self.db.query(CommunityInvitation)
            .filter(
                CommunityInvitation.community_id == community_id,
                CommunityInvitation.inviter_id == current_user.id,
                CommunityInvitation.status == "pending",
            )
            .count()
        )
        if active_invitations + len(invitations) > settings.MAX_PENDING_INVITATIONS:
            raise HTTPException(
                status_code=400,
                detail=(
                    f"Cannot send more than {settings.MAX_PENDING_INVITATIONS} "
                    "pending invitations"
                ),
            )

        created: List[CommunityInvitation] = []
        for invitation in invitations:
            invitee = (
                self.db.query(User).filter(User.id == invitation.invitee_id).first()
            )
            if not invitee:
                continue

            existing_invitation = (
                self.db.query(CommunityInvitation)
                .filter(
                    CommunityInvitation.community_id == community_id,
                    CommunityInvitation.invitee_id == invitation.invitee_id,
                    CommunityInvitation.status == "pending",
                )
                .first()
            )
            if existing_invitation:
                continue

            is_member = (
                self.db.query(CommunityMember)
                .filter(
                    CommunityMember.community_id == community_id,
                    CommunityMember.user_id == invitation.invitee_id,
                )
                .first()
            )
            if is_member:
                continue

            new_invitation = CommunityInvitation(
                community_id=community_id,
                inviter_id=current_user.id,
                invitee_id=invitation.invitee_id,
            )
            self.db.add(new_invitation)
            created.append(new_invitation)

            create_notification(
                self.db,
                invitation.invitee_id,
                (
                    f"You have an invitation to join community {community.name} "
                    f"from {get_user_display_name(current_user)}"
                ),
                "/invitations",
                "community_invitation",
                new_invitation.id,
            )

        self.db.commit()
        for invitation in created:
            self.db.refresh(invitation)

        return created

    def respond_to_invitation(
        self,
        *,
        invitation_id: int,
        current_user: User,
        accept: bool,
    ) -> dict:
        invitation = (
            self.db.query(CommunityInvitation)
            .filter(CommunityInvitation.id == invitation_id)
            .first()
        )
        if not invitation:
            raise HTTPException(status_code=404, detail="Invitation not found")

        if invitation.invitee_id != current_user.id:
            raise HTTPException(
                status_code=403,
                detail="You are not allowed to respond to this invitation",
            )

        if invitation.status != "pending":
            raise HTTPException(
                status_code=400, detail="This invitation has already been processed"
            )

        community = invitation.community
        if not community:
            raise HTTPException(status_code=404, detail="Community not found")

        if accept:
            existing_member = (
                self.db.query(CommunityMember)
                .filter(
                    CommunityMember.community_id == community.id,
                    CommunityMember.user_id == current_user.id,
                )
                .first()
            )
            if existing_member:
                raise HTTPException(
                    status_code=400,
                    detail="You are already a member of this community",
                )

            new_member = CommunityMember(
                community_id=community.id,
                user_id=current_user.id,
                role=CommunityRole.MEMBER,
                join_date=datetime.now(timezone.utc),
            )
            self.db.add(new_member)

            invitation.status = "accepted"
            invitation.accepted_at = datetime.now(timezone.utc)

            create_notification(
                self.db,
                community.owner_id,
                f"{get_user_display_name(current_user)} accepted the invitation to join {community.name}",
                f"/community/{community.id}",
                "invitation_accepted",
                invitation.id,
            )
            message = "Invitation accepted and you have joined the community"
        else:
            invitation.status = "declined"
            message = "Invitation declined"

        self.db.commit()
        return {"message": message}

    def leave_community(
        self,
        *,
        community_id: int,
        current_user: User,
    ) -> dict:
        community = (
            self.db.query(Community)
            .options(joinedload(Community.members))
            .filter(Community.id == community_id)
            .first()
        )
        if not community:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail="Community not found"
            )

        member = (
            self.db.query(CommunityMember)
            .filter(
                CommunityMember.community_id == community_id,
                CommunityMember.user_id == current_user.id,
            )
            .first()
        )
        if not member:
            raise HTTPException(
                status_code=400, detail="You are not a member of this community"
            )

        if member.role == CommunityRole.OWNER:
            raise HTTPException(
                status_code=403, detail="Owners cannot leave their own community"
            )

        self.db.delete(member)
        self.db.commit()

        create_notification(
            self.db,
            community.owner_id,
            f"{get_user_display_name(current_user)} has left the community {community.name}",
            f"/community/{community.id}",
            "member_left",
            current_user.id,
        )

        return {"message": "You have left the community"}

    def cleanup_expired_invitations(self) -> int:
        expired_invitations = (
            self.db.query(CommunityInvitation)
            .filter(
                CommunityInvitation.status == "pending",
                CommunityInvitation.expires_at <= datetime.now(timezone.utc),
            )
            .all()
        )

        for invitation in expired_invitations:
            invitation.status = "expired"
            create_notification(
                self.db,
                invitation.invitee_id,
                f"Your invitation to join community {invitation.community.name} has expired",
                f"/community/{invitation.community_id}",
                "invitation_expired",
                invitation.id,
            )

        self.db.commit()
        return len(expired_invitations)

    def _ensure_permissions(
        self,
        user: User,
        community: Community,
        required_role: CommunityRole,
    ) -> bool:
        if not community:
            raise HTTPException(status_code=404, detail="Community not found")

        member = next((m for m in community.members if m.user_id == user.id), None)
        if not member:
            raise HTTPException(
                status_code=403,
                detail="You must be a member of the community to perform this action",
            )

        if member.role not in {
            required_role,
            CommunityRole.ADMIN,
            CommunityRole.OWNER,
        }:
            raise HTTPException(
                status_code=403,
                detail="You do not have sufficient permissions to perform this action",
            )

        return True

    def join_community(
        self,
        *,
        community_id: int,
        current_user: User,
    ) -> dict:
        community = (
            self.db.query(Community)
            .options(joinedload(Community.members))
            .filter(Community.id == community_id)
            .first()
        )
        if not community:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail="Community not found"
            )

        member = next(
            (m for m in community.members if m.user_id == current_user.id), None
        )
        if member:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="You are already a member of this community",
            )

        invitation = None
        if community.is_private:
            invitation = (
                self.db.query(CommunityInvitation)
                .filter(
                    CommunityInvitation.community_id == community_id,
                    CommunityInvitation.invitee_id == current_user.id,
                    CommunityInvitation.status == "pending",
                )
                .first()
            )
            if not invitation:
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="This is a private community and requires an invitation to join",
                )

        new_member = CommunityMember(
            community_id=community_id,
            user_id=current_user.id,
            role=CommunityRole.MEMBER,
            join_date=datetime.now(timezone.utc),
        )

        self.db.add(new_member)
        community.members.append(new_member)

        if community.is_private and invitation:
            invitation.status = "accepted"
            invitation.accepted_at = datetime.now(timezone.utc)

        self.db.commit()

        create_notification(
            self.db,
            community.owner_id,
            f"{get_user_display_name(current_user)} has joined the community {community.name}",
            f"/community/{community_id}",
            "new_member",
            current_user.id,
        )

        return {"message": "Successfully joined the community"}

    def create_community_post(
        self,
        *,
        community_id: int,
        payload: PostCreate,
        current_user: User,
    ) -> Post:
        community = (
            self.db.query(Community)
            .options(joinedload(Community.members), joinedload(Community.rules))
            .filter(Community.id == community_id)
            .first()
        )
        if not community:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail="Community not found"
            )

        member = next(
            (m for m in community.members if m.user_id == current_user.id), None
        )
        if not member:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="You must be a member of the community to create a post",
            )

        content = (payload.content or "").strip()
        if not content:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Post content cannot be empty",
            )

        if check_for_profanity(content):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Content contains inappropriate language",
            )

        existing_rules = [
            getattr(rule, "content", None) or getattr(rule, "rule", None)
            for rule in community.rules
        ]
        existing_rules = [r for r in existing_rules if r]
        if existing_rules and not check_content_against_rules(content, existing_rules):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Content violates community rules",
            )

        post_data = payload.model_dump(
            exclude={
                "community_id",
                "hashtags",
                "mentioned_usernames",
                "is_help_request",
                "analyze_content",
                "related_to_post_id",
                "relation_type",
            }
        )

        new_post = Post(
            owner_id=current_user.id,
            community_id=community_id,
            **post_data,
        )

        self.db.add(new_post)
        self.db.commit()
        self.db.refresh(new_post)

        if getattr(payload, "analyze_content", False):
            analysis_result = analyze_content(content)
            new_post.sentiment = analysis_result["sentiment"]["sentiment"]
            new_post.sentiment_score = analysis_result["sentiment"]["score"]
            new_post.content_suggestion = analysis_result["suggestion"]
            self.db.commit()
            self.db.refresh(new_post)

        if not getattr(new_post, "privacy_level", None):
            new_post.privacy_level = PrivacyLevel.PUBLIC
        if not hasattr(new_post, "poll_data"):
            new_post.poll_data = None

        member_post_count = (
            self.db.query(func.count(Post.id))
            .filter(
                Post.community_id == community_id,
                Post.owner_id == current_user.id,
            )
            .scalar()
            or 0
        )

        if (
            member.role == CommunityRole.MEMBER
            and member_post_count >= ACTIVITY_THRESHOLD_VIP
        ):
            member.role = CommunityRole.VIP
            self.db.commit()
            create_notification(
                self.db,
                current_user.id,
                f"You have been upgraded to VIP in community {community.name}",
                f"/community/{community_id}",
                "role_upgrade",
                None,
            )

        for admin_member in community.members:
            if admin_member.role in {CommunityRole.ADMIN, CommunityRole.OWNER}:
                create_notification(
                    self.db,
                    admin_member.user_id,
                    f"New post by {get_user_display_name(current_user)} in community {community.name}",
                    f"/post/{new_post.id}",
                    "new_post",
                    new_post.id,
                )

        return new_post

    def update_community_statistics(self, *, community_id: int) -> CommunityStatistics:
        today = date.today()
        stats = (
            self.db.query(CommunityStatistics)
            .filter(
                CommunityStatistics.community_id == community_id,
                CommunityStatistics.date == today,
            )
            .first()
        )
        if not stats:
            stats = CommunityStatistics(community_id=community_id, date=today)
            self.db.add(stats)

        stats.member_count = (
            self.db.query(CommunityMember)
            .filter(CommunityMember.community_id == community_id)
            .count()
        )

        # Use cumulative counts to avoid missing data when timestamps fall outside local date boundaries.
        stats.post_count = (
            self.db.query(Post).filter(Post.community_id == community_id).count()
        )

        stats.comment_count = (
            self.db.query(Comment)
            .join(Post, Comment.post_id == Post.id)
            .filter(Post.community_id == community_id)
            .count()
        )

        last_active_col = getattr(CommunityMember, "last_active_at", None)
        if last_active_col is not None:
            stats.active_users = (
                self.db.query(CommunityMember)
                .filter(
                    CommunityMember.community_id == community_id,
                    last_active_col >= today - timedelta(days=30),
                )
                .count()
            )
        else:
            stats.active_users = stats.member_count

        vote_filters = [Post.community_id == community_id]
        vote_date_col = getattr(Vote, "created_at", None)
        vote_query = self.db.query(func.count(Vote.user_id)).join(
            Post, Vote.post_id == Post.id
        )
        if vote_date_col is not None:
            vote_filters.append(func.date(vote_date_col) == today)
        stats.total_reactions = vote_query.filter(*vote_filters).scalar() or 0

        if stats.active_users > 0:
            stats.average_posts_per_user = round(
                stats.post_count / stats.active_users, 2
            )
        else:
            stats.average_posts_per_user = 0

        engagement_rate = (
            round(
                (stats.comment_count + stats.total_reactions)
                / stats.member_count
                * 100,
                2,
            )
            if stats.member_count > 0
            else 0
        )
        if hasattr(stats, "engagement_rate"):
            stats.engagement_rate = engagement_rate

        self.db.commit()
        self.db.refresh(stats)
        return stats

    def update_community_rankings(self) -> None:
        communities = self.db.query(Community).all()
        now = datetime.now(timezone.utc)
        for community in communities:
            posts_count = getattr(community, "posts_count", 0) or 0
            comment_count = getattr(community, "comment_count", 0) or 0
            members_count = getattr(community, "members_count", None)
            if members_count is None:
                members_count = len(getattr(community, "members", []))
            total_reactions = getattr(community, "total_reactions", 0) or 0

            activity_score = (
                posts_count * 2
                + comment_count * 1
                + members_count * 3
                + total_reactions
            )
            growth_rate = self.calculate_community_growth_rate(community.id)
            created_at = getattr(community, "created_at", None)
            if created_at:
                age_in_days = max((now - created_at).days, 0)
            else:
                age_in_days = getattr(community, "age_in_days", 0) or 0

            community.activity_score = activity_score
            community.growth_rate = growth_rate
            community.ranking = self.calculate_community_ranking(
                activity_score, growth_rate, age_in_days
            )

        self.db.commit()

    @staticmethod
    def calculate_community_ranking(
        activity_score: float, growth_rate: float, age_in_days: int
    ) -> float:
        age_factor = min(1.0, age_in_days / 365) if age_in_days else 0
        ranking = (activity_score * 0.4) + (growth_rate * 0.4) + (age_factor * 0.2)
        return round(ranking, 2)

    def calculate_community_growth_rate(self, community_id: int) -> float:
        now = datetime.now(timezone.utc)
        current_month_start = now.replace(
            day=1, hour=0, minute=0, second=0, microsecond=0
        )
        previous_month_start = (current_month_start - timedelta(days=1)).replace(day=1)

        current_stats = self.get_community_monthly_stats(
            community_id=community_id, period_start=current_month_start
        )
        previous_stats = self.get_community_monthly_stats(
            community_id=community_id, period_start=previous_month_start
        )

        if previous_stats["members"] == 0:
            return 100.0 if current_stats["members"] > 0 else 0.0

        growth_rates = {
            "members": (
                (current_stats["members"] - previous_stats["members"])
                / previous_stats["members"]
            )
            * 100,
            "posts": (
                (
                    (current_stats["posts"] - previous_stats["posts"])
                    / previous_stats["posts"]
                )
                * 100
                if previous_stats["posts"] > 0
                else (100.0 if current_stats["posts"] > 0 else 0.0)
            ),
            "engagement": (
                (
                    (current_stats["engagement"] - previous_stats["engagement"])
                    / previous_stats["engagement"]
                )
                * 100
                if previous_stats["engagement"] > 0
                else (100.0 if current_stats["engagement"] > 0 else 0.0)
            ),
        }

        weighted_growth = (
            (growth_rates["members"] * 0.4)
            + (growth_rates["posts"] * 0.3)
            + (growth_rates["engagement"] * 0.3)
        )
        return round(weighted_growth, 2)

    def get_community_monthly_stats(
        self, *, community_id: int, period_start: datetime
    ) -> Dict[str, float]:
        period_end = (period_start + timedelta(days=32)).replace(day=1)
        aggregates = (
            self.db.query(
                func.max(CommunityStatistics.member_count).label("members"),
                func.sum(CommunityStatistics.post_count).label("posts"),
                func.sum(
                    CommunityStatistics.comment_count
                    + CommunityStatistics.total_reactions
                ).label("engagement"),
            )
            .filter(
                CommunityStatistics.community_id == community_id,
                CommunityStatistics.date >= period_start.date(),
                CommunityStatistics.date < period_end.date(),
            )
            .one()
        )

        members = aggregates.members or 0
        posts = aggregates.posts or 0
        engagement = aggregates.engagement or 0

        return {
            "members": members,
            "posts": posts,
            "engagement": engagement,
        }

    def create_instant_community(
        self, *, current_user: User, topic: str, duration_hours: int = 24
    ) -> Community:
        """
        Creates a temporary community focused on a specific trending topic.
        Part of 'Liquid Communities'.
        """
        # Generate a unique name based on topic and timestamp
        timestamp_str = datetime.now(timezone.utc).strftime("%Y%m%d%H%M")
        name = f"Instant-{topic[:10]}-{timestamp_str}"

        expires_at = datetime.now(timezone.utc) + timedelta(hours=duration_hours)

        new_community = Community(
            name=name,
            description=f"Instant community for topic: {topic}",
            owner_id=current_user.id,
            is_active=True,
            is_temporary=True,
            expires_at=expires_at,
            privacy_level="public",  # Assuming logic fits existing constraints
        )

        # Add owner as member
        owner_member = CommunityMember(
            user_id=current_user.id,
            role=CommunityRole.OWNER,
            join_date=datetime.now(timezone.utc),
        )
        new_community.members.append(owner_member)

        self.db.add(new_community)
        self.db.commit()
        self.db.refresh(new_community)

        return new_community

    def export_community_data(
        self,
        *,
        community_id: int,
        data_type: str,
        current_user: User,
        date_from: Optional[date],
        date_to: Optional[date],
    ) -> Tuple[str, str]:
        if data_type not in {"members", "posts", "analytics"}:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid data type requested",
            )

        community = (
            self.db.query(Community)
            .options(joinedload(Community.members))
            .filter(Community.id == community_id)
            .first()
        )
        if not community:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail="Community not found"
            )

        self._ensure_permissions(current_user, community, CommunityRole.ADMIN)

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
            for member in community.members:
                role_attr = getattr(member, "role", CommunityRole.MEMBER)
                role_display = (
                    role_attr.value
                    if isinstance(role_attr, CommunityRole)
                    else role_attr
                )
                joined_at = getattr(member, "join_date", None) or getattr(
                    member, "joined_at", None
                )
                posts_count = getattr(member, "posts_count", 0)
                activity_score = getattr(member, "activity_score", 0)
                last_active_at = getattr(member, "last_active_at", None)
                writer.writerow(
                    [
                        member.user_id,
                        member.user.username if member.user else "Unknown",
                        role_display,
                        joined_at.strftime("%Y-%m-%d") if joined_at else "N/A",
                        posts_count,
                        activity_score,
                        (
                            last_active_at.strftime("%Y-%m-%d %H:%M")
                            if last_active_at
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
            query = self.db.query(Post).filter(Post.community_id == community_id)
            if date_from:
                query = query.filter(
                    Post.created_at >= datetime.combine(date_from, datetime.min.time())
                )
            if date_to:
                query = query.filter(
                    Post.created_at <= datetime.combine(date_to, datetime.max.time())
                )
            for post in query.all():
                writer.writerow(
                    [
                        post.id,
                        post.owner.username if post.owner else "Unknown",
                        post.created_at.strftime("%Y-%m-%d %H:%M"),
                        getattr(post, "likes_count", 0),
                        getattr(post, "comments_count", 0),
                        getattr(post, "content_type", "text"),
                        getattr(post, "status", "published"),
                    ]
                )

        else:  # analytics
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
            start = date_from or (datetime.now() - timedelta(days=30)).date()
            end = date_to or datetime.now().date()
            stats = (
                self.db.query(CommunityStatistics)
                .filter(
                    CommunityStatistics.community_id == community_id,
                    CommunityStatistics.date.between(start, end),
                )
                .order_by(CommunityStatistics.date)
                .all()
            )
            for stat in stats:
                member_count = stat.member_count or 0
                if member_count > 0:
                    engagement_rate = (
                        (stat.comment_count + stat.total_reactions) / member_count * 100
                    )
                else:
                    engagement_rate = 0.0
                writer.writerow(
                    [
                        stat.date.strftime("%Y-%m-%d"),
                        member_count,
                        stat.post_count or 0,
                        stat.comment_count or 0,
                        stat.active_users or 0,
                        stat.total_reactions or 0,
                        f"{engagement_rate:.2f}%",
                    ]
                )

        output.seek(0)
        filename = f"community_{community_id}_{data_type}_{datetime.now().strftime('%Y%m%d')}.csv"
        return output.getvalue(), filename
