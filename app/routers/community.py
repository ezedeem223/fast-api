from fastapi import (
    APIRouter,
    Depends,
    HTTPException,
    status,
    Query,
    Request,
    Body,
    Response,
)
from sqlalchemy.orm import Session, joinedload
from typing import List, Union
from .. import models, schemas, oauth2
from ..database import get_db
from ..utils import log_user_event, create_notification, get_translated_content
import logging
from datetime import date, timedelta
from sqlalchemy import func
from fastapi.responses import HTMLResponse, StreamingResponse
import csv
from io import StringIO

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/communities", tags=["Communities"])


@router.post(
    "/", status_code=status.HTTP_201_CREATED, response_model=schemas.CommunityOut
)
def create_community(
    community: schemas.CommunityCreate,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(oauth2.get_current_user),
):
    new_community = models.Community(
        owner_id=current_user.id, **community.dict(exclude={"tags"})
    )
    new_community.members.append(current_user)

    if community.category_id:
        category = (
            db.query(models.Category)
            .filter(models.Category.id == community.category_id)
            .first()
        )
        if not category:
            raise HTTPException(status_code=404, detail="Category not found")
        new_community.category = category

    for tag_id in community.tags:
        tag = db.query(models.Tag).filter(models.Tag.id == tag_id).first()
        if tag:
            new_community.tags.append(tag)

    db.add(new_community)
    db.commit()
    db.refresh(new_community)

    log_user_event(
        db, current_user.id, "create_community", {"community_id": new_community.id}
    )

    create_notification(
        db,
        current_user.id,
        f"Вы создали новое сообщество: {new_community.name}",
        f"/community/{new_community.id}",
        "new_community",
        new_community.id,
    )

    return schemas.CommunityOut.from_orm(new_community)


@router.get("/", response_model=List[schemas.CommunityOut])
async def get_communities(
    db: Session = Depends(get_db),
    current_user: models.User = Depends(oauth2.get_current_user),
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=100),
    search: str = "",
):
    query = db.query(models.Community)
    if search:
        query = query.filter(models.Community.name.ilike(f"%{search}%"))
    communities = query.offset(skip).limit(limit).all()

    for community in communities:
        community.name = await get_translated_content(
            community.name, current_user, community.language
        )
        community.description = await get_translated_content(
            community.description, current_user, community.language
        )

    return [schemas.CommunityOut.from_orm(community) for community in communities]


@router.get("/{id}", response_model=schemas.CommunityOut)
async def get_community(
    id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(oauth2.get_current_user),
):
    community = db.query(models.Community).filter(models.Community.id == id).first()
    if not community:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Community with id: {id} was not found",
        )
    community.name = await get_translated_content(
        community.name, current_user, community.language
    )
    community.description = await get_translated_content(
        community.description, current_user, community.language
    )

    return schemas.CommunityOut.from_orm(community)


@router.put("/{id}", response_model=schemas.CommunityOut)
def update_community(
    id: int,
    updated_community: schemas.CommunityUpdate,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(oauth2.get_current_user),
):
    community_query = db.query(models.Community).filter(models.Community.id == id)
    community = community_query.first()
    if community is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Community with id: {id} does not exist",
        )
    if community.owner_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Not authorized to perform requested action",
        )

    update_data = updated_community.dict(exclude_unset=True)

    if "category_id" in update_data:
        category = (
            db.query(models.Category)
            .filter(models.Category.id == update_data["category_id"])
            .first()
        )
        if not category:
            raise HTTPException(status_code=404, detail="Category not found")
        community.category = category
        del update_data["category_id"]

    if "tags" in update_data:
        community.tags.clear()
        for tag_id in update_data["tags"]:
            tag = db.query(models.Tag).filter(models.Tag.id == tag_id).first()
            if tag:
                community.tags.append(tag)
        del update_data["tags"]

    community_query.update(update_data, synchronize_session=False)
    db.commit()
    db.refresh(community)

    create_notification(
        db,
        current_user.id,
        f"Вы обновили сообщество: {community.name}",
        f"/community/{community.id}",
        "update_community",
        community.id,
    )

    return schemas.CommunityOut.from_orm(community)


@router.delete("/{id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_community(
    id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(oauth2.get_current_user),
):
    community_query = db.query(models.Community).filter(models.Community.id == id)
    community = community_query.first()
    if community is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Community with id: {id} does not exist",
        )
    if community.owner_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Not authorized to perform requested action",
        )
    community_query.delete(synchronize_session=False)
    db.commit()

    create_notification(
        db,
        current_user.id,
        f"Вы удалили сообщество: {community.name}",
        "/communities",
        "delete_community",
        None,
    )

    return {"message": "Community deleted successfully"}


@router.post("/{id}/join", status_code=status.HTTP_200_OK)
def join_community(
    id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(oauth2.get_current_user),
):
    community = db.query(models.Community).filter(models.Community.id == id).first()
    if not community:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Community with id: {id} was not found",
        )
    if current_user in community.members:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="User is already a member of this community",
        )
    community.members.append(current_user)
    db.commit()
    db.refresh(community)

    create_notification(
        db,
        current_user.id,
        f"Вы присоединились к сообществу: {community.name}",
        f"/community/{community.id}",
        "join_community",
        community.id,
    )

    return {"message": "Joined the community successfully"}


@router.post("/{id}/leave", status_code=status.HTTP_200_OK)
def leave_community(
    id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(oauth2.get_current_user),
):
    community = db.query(models.Community).filter(models.Community.id == id).first()
    if not community:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Community with id: {id} was not found",
        )
    if current_user not in community.members:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="User is not a member of this community",
        )
    if community.owner_id == current_user.id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Owner cannot leave the community",
        )
    community.members.remove(current_user)
    db.commit()
    db.refresh(community)

    create_notification(
        db,
        current_user.id,
        f"Вы покинули сообщество: {community.name}",
        f"/community/{community.id}",
        "leave_community",
        community.id,
    )

    return {"message": "Left the community successfully"}


@router.post(
    "/{community_id}/reels",
    status_code=status.HTTP_201_CREATED,
    response_model=schemas.ReelOut,
)
@router.post(
    "/{community_id}/articles",
    status_code=status.HTTP_201_CREATED,
    response_model=schemas.ArticleOut,
)
async def create_content(
    community_id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(oauth2.get_current_user),
    content: Union[schemas.ReelCreate, schemas.ArticleCreate] = Body(...),
):
    community = (
        db.query(models.Community).filter(models.Community.id == community_id).first()
    )
    if not community:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Community with id: {community_id} not found",
        )

    if current_user not in community.members:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You must be a member of the community to create content",
        )

    content_type = content.__class__.__name__.replace("Create", "")
    model = getattr(models, content_type)

    if content_type == "Article":
        new_content = model(
            author_id=current_user.id,
            community_id=community_id,
            **content.dict(exclude={"community_id"}),
        )
    else:
        new_content = model(
            owner_id=current_user.id,
            community_id=community_id,
            **content.dict(exclude={"community_id"}),
        )

    db.add(new_content)
    db.commit()
    db.refresh(new_content)

    create_notification(
        db,
        community.owner_id,
        f"Новый контент в вашем сообществе: {community.name}",
        f"/community/{community_id}",
        f"new_{content_type.lower()}",
        new_content.id,
    )

    response_schema = getattr(schemas, f"{content_type}Out")
    return response_schema.from_orm(new_content)


@router.get("/{community_id}/reels", response_model=List[schemas.ReelOut])
@router.get("/{community_id}/articles", response_model=List[schemas.ArticleOut])
@router.get("/{community_id}/posts", response_model=List[schemas.PostOut])
async def get_community_content(
    request: Request,
    community_id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(oauth2.get_current_user),
    skip: int = Query(0, ge=0),
    limit: int = Query(20, ge=1, le=100),
):
    community = (
        db.query(models.Community).filter(models.Community.id == community_id).first()
    )
    if not community:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Community not found"
        )

    content_type = request.url.path.split("/")[-1]  # reels, articles, or posts
    model = getattr(models, content_type.capitalize()[:-1])  # Reel, Article, or Post
    content = (
        db.query(model)
        .filter(model.community_id == community_id)
        .offset(skip)
        .limit(limit)
        .all()
    )
    for item in content:
        if hasattr(item, "title"):
            item.title = await get_translated_content(
                item.title, current_user, item.language
            )
        if hasattr(item, "content"):
            item.content = await get_translated_content(
                item.content, current_user, item.language
            )
        if hasattr(item, "description"):
            item.description = await get_translated_content(
                item.description, current_user, item.language
            )

    response_schema = getattr(schemas, f"{content_type.capitalize()[:-1]}Out")
    return [
        response_schema(
            **item.__dict__,
            owner=(
                schemas.UserOut.from_orm(item.owner)
                if content_type != "articles"
                else None
            ),
            author=(
                schemas.UserOut.from_orm(item.author)
                if content_type == "articles"
                else None
            ),
            community=schemas.CommunityOut.from_orm(community),
        )
        for item in content
    ]


def create_community_post(
    community_id: int,
    post: schemas.PostCreate,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(oauth2.get_current_user),
):
    community = (
        db.query(models.Community).filter(models.Community.id == community_id).first()
    )
    if not community:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Community not found"
        )

    if current_user not in community.members:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You must be a member of the community to create a post",
        )

    new_post = models.Post(
        owner_id=current_user.id,
        community_id=community_id,
        **post.dict(exclude={"community_id"}),
    )
    db.add(new_post)
    db.commit()
    db.refresh(new_post)

    create_notification(
        db,
        community.owner_id,
        f"Новый пост в вашем сообществе: {community.name}",
        f"/post/{new_post.id}",
        "new_community_post",
        new_post.id,
    )
    return schemas.PostOut(
        **new_post.__dict__,
        owner=schemas.UserOut.from_orm(current_user),
        community=schemas.CommunityOut.from_orm(community),
    )


@router.post(
    "/{community_id}/invite",
    status_code=status.HTTP_201_CREATED,
    response_model=schemas.CommunityInvitationOut,
)
def invite_friend_to_community(
    community_id: int,
    invitation: schemas.CommunityInvitationCreate,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(oauth2.get_current_user),
):
    community = (
        db.query(models.Community).filter(models.Community.id == community_id).first()
    )
    if not community:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Community not found"
        )

    if current_user not in community.members:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You must be a member of the community to invite friends",
        )

    invitee = (
        db.query(models.User).filter(models.User.id == invitation.invitee_id).first()
    )
    if not invitee:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Invitee not found"
        )

    if invitee in community.members:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="User is already a member of this community",
        )

    new_invitation = models.CommunityInvitation(
        community_id=community_id,
        inviter_id=current_user.id,
        invitee_id=invitation.invitee_id,
    )
    db.add(new_invitation)
    db.commit()
    db.refresh(new_invitation)

    create_notification(
        db,
        invitation.invitee_id,
        f"Вас пригласили в сообщество: {community.name}",
        f"/community/{community_id}",
        "community_invitation",
        new_invitation.id,
    )
    return schemas.CommunityInvitationOut.from_orm(new_invitation)


@router.get("/user-invitations", response_model=List[schemas.CommunityInvitationOut])
async def get_user_invitations(
    request: Request,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(oauth2.get_current_user),
):
    logger.info(f"Fetching invitations for user {current_user.id}")
    invitations = (
        db.query(models.CommunityInvitation)
        .filter(
            models.CommunityInvitation.invitee_id == current_user.id,
            models.CommunityInvitation.status == "pending",
        )
        .options(
            joinedload(models.CommunityInvitation.community).joinedload(
                models.Community.owner
            ),
            joinedload(models.CommunityInvitation.inviter),
            joinedload(models.CommunityInvitation.invitee),
        )
        .all()
    )
    logger.info(f"Found {len(invitations)} invitations")

    result = []
    for invitation in invitations:
        invitation_dict = {
            "id": invitation.id,
            "community_id": invitation.community_id,
            "inviter_id": invitation.inviter_id,
            "invitee_id": invitation.invitee_id,
            "status": invitation.status,
            "created_at": invitation.created_at,
            "community": schemas.CommunityOut.from_orm(invitation.community),
            "inviter": schemas.UserOut.from_orm(invitation.inviter),
            "invitee": schemas.UserOut.from_orm(invitation.invitee),
        }
        result.append(schemas.CommunityInvitationOut(**invitation_dict))

    return result


@router.post("/invitations/{invitation_id}/accept", status_code=status.HTTP_200_OK)
def accept_invitation(
    invitation_id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(oauth2.get_current_user),
):
    invitation = (
        db.query(models.CommunityInvitation)
        .filter(
            models.CommunityInvitation.id == invitation_id,
            models.CommunityInvitation.invitee_id == current_user.id,
        )
        .first()
    )
    if not invitation:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Invitation not found"
        )

    if invitation.status != "pending":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invitation has already been processed",
        )

    community = (
        db.query(models.Community)
        .filter(models.Community.id == invitation.community_id)
        .first()
    )
    community.members.append(current_user)
    invitation.status = "accepted"
    db.commit()

    create_notification(
        db,
        invitation.inviter_id,
        f"{current_user.username} принял(а) ваше приглашение в сообщество {community.name}",
        f"/community/{community.id}",
        "invitation_accepted",
        invitation.id,
    )
    return {"message": "Invitation accepted successfully"}


@router.post("/invitations/{invitation_id}/reject", status_code=status.HTTP_200_OK)
def reject_invitation(
    invitation_id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(oauth2.get_current_user),
):
    invitation = (
        db.query(models.CommunityInvitation)
        .filter(
            models.CommunityInvitation.id == invitation_id,
            models.CommunityInvitation.invitee_id == current_user.id,
        )
        .first()
    )
    if not invitation:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Invitation not found"
        )

    if invitation.status != "pending":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invitation has already been processed",
        )

    invitation.status = "rejected"
    db.commit()
    create_notification(
        db,
        invitation.inviter_id,
        f"{current_user.username} отклонил(а) ваше приглашение в сообщество",
        f"/community/{invitation.community_id}",
        "invitation_rejected",
        invitation.id,
    )
    return {"message": "Invitation rejected successfully"}


@router.put(
    "/{community_id}/members/{user_id}/role", response_model=schemas.CommunityMemberOut
)
def update_member_role(
    community_id: int,
    user_id: int,
    role_update: schemas.CommunityMemberUpdate,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(oauth2.get_current_user),
):
    community = (
        db.query(models.Community).filter(models.Community.id == community_id).first()
    )
    if not community:
        raise HTTPException(status_code=404, detail="Community not found")

    if community.owner_id != current_user.id:
        raise HTTPException(
            status_code=403, detail="Only the community owner can update roles"
        )

    member = (
        db.query(models.CommunityMember)
        .filter(
            models.CommunityMember.community_id == community_id,
            models.CommunityMember.user_id == user_id,
        )
        .first()
    )

    if not member:
        raise HTTPException(
            status_code=404, detail="Member not found in this community"
        )

    if role_update.role == models.CommunityRole.OWNER:
        raise HTTPException(status_code=400, detail="Cannot set a member as owner")

    member.role = role_update.role
    db.commit()
    db.refresh(member)

    create_notification(
        db,
        user_id,
        f"Ваша роль в сообществе {community.name} изменена на {role_update.role}",
        f"/community/{community_id}",
        "role_updated",
        community_id,
    )
    return schemas.CommunityMemberOut.from_orm(member)


@router.get("/{community_id}/members", response_model=List[schemas.CommunityMemberOut])
def get_community_members(
    community_id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(oauth2.get_current_user),
):
    community = (
        db.query(models.Community).filter(models.Community.id == community_id).first()
    )
    if not community:
        raise HTTPException(status_code=404, detail="Community not found")

    members = (
        db.query(models.CommunityMember)
        .filter(models.CommunityMember.community_id == community_id)
        .all()
    )

    return [schemas.CommunityMemberOut.from_orm(member) for member in members]


@router.post("/{community_id}/update-activity")
def update_member_activity(
    community_id: int,
    user_id: int,
    activity_score: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(oauth2.get_current_user),
):
    community = (
        db.query(models.Community).filter(models.Community.id == community_id).first()
    )
    if not community:
        raise HTTPException(status_code=404, detail="Community not found")

    member = (
        db.query(models.CommunityMember)
        .filter(
            models.CommunityMember.community_id == community_id,
            models.CommunityMember.user_id == user_id,
        )
        .first()
    )

    if not member:
        raise HTTPException(
            status_code=404, detail="Member not found in this community"
        )

    member.activity_score += activity_score

    # Check if member should be promoted to VIP
    if member.activity_score >= 1000 and member.role == models.CommunityRole.MEMBER:
        member.role = models.CommunityRole.VIP

    create_notification(
        db,
        user_id,
        f"Поздравляем! Вы стали VIP-участником сообщества {community.name}",
        f"/community/{community_id}",
        "vip_status",
        community_id,
    )
    db.commit()
    db.refresh(member)

    return {"message": "Activity score updated successfully"}


@router.post("/{community_id}/rules", response_model=schemas.CommunityRuleOut)
def add_community_rule(
    community_id: int,
    rule: schemas.CommunityRuleCreate,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(oauth2.get_current_user),
):
    community = (
        db.query(models.Community).filter(models.Community.id == community_id).first()
    )
    if not community:
        raise HTTPException(status_code=404, detail="Community not found")

    if community.owner_id != current_user.id:
        raise HTTPException(
            status_code=403, detail="Only the community owner can add rules"
        )

    new_rule = models.CommunityRule(community_id=community_id, **rule.dict())
    db.add(new_rule)
    db.commit()
    db.refresh(new_rule)
    for member in community.members:
        create_notification(
            db,
            member.id,
            f"Новое правило добавлено в сообщество {community.name}",
            f"/community/{community_id}",
            "new_rule",
            new_rule.id,
        )
    return new_rule


@router.put("/{community_id}/rules/{rule_id}", response_model=schemas.CommunityRuleOut)
def update_community_rule(
    community_id: int,
    rule_id: int,
    rule: schemas.CommunityRuleUpdate,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(oauth2.get_current_user),
):
    community = (
        db.query(models.Community).filter(models.Community.id == community_id).first()
    )
    if not community:
        raise HTTPException(status_code=404, detail="Community not found")

    if community.owner_id != current_user.id:
        raise HTTPException(
            status_code=403, detail="Only the community owner can update rules"
        )

    db_rule = (
        db.query(models.CommunityRule)
        .filter(
            models.CommunityRule.id == rule_id,
            models.CommunityRule.community_id == community_id,
        )
        .first()
    )
    if not db_rule:
        raise HTTPException(status_code=404, detail="Rule not found")

    for key, value in rule.dict().items():
        setattr(db_rule, key, value)

    db.commit()
    db.refresh(db_rule)
    for member in community.members:
        create_notification(
            db,
            member.id,
            f"Правило сообщества {community.name} было обновлено",
            f"/community/{community_id}",
            "rule_updated",
            rule_id,
        )
    return db_rule


@router.delete("/{community_id}/rules/{rule_id}", status_code=204)
def delete_community_rule(
    community_id: int,
    rule_id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(oauth2.get_current_user),
):
    community = (
        db.query(models.Community).filter(models.Community.id == community_id).first()
    )
    if not community:
        raise HTTPException(status_code=404, detail="Community not found")

    if community.owner_id != current_user.id:
        raise HTTPException(
            status_code=403, detail="Only the community owner can delete rules"
        )

    db_rule = (
        db.query(models.CommunityRule)
        .filter(
            models.CommunityRule.id == rule_id,
            models.CommunityRule.community_id == community_id,
        )
        .first()
    )
    if not db_rule:
        raise HTTPException(status_code=404, detail="Rule not found")

    db.delete(db_rule)
    db.commit()
    for member in community.members:
        create_notification(
            db,
            member.id,
            f"Правило в сообществе {community.name} было удалено",
            f"/community/{community_id}",
            "rule_deleted",
            rule_id,
        )
    return Response(status_code=204)


def update_community_statistics(db: Session, community_id: int):
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

    # إضافة إحصائيات جديدة
    stats.total_reactions = (
        db.query(func.count(models.Vote.id))
        .join(models.Post)
        .filter(
            models.Post.community_id == community_id,
            func.date(models.Vote.created_at) == today,
        )
        .scalar()
    )

    if stats.active_users > 0:
        stats.average_posts_per_user = stats.post_count / stats.active_users
    else:
        stats.average_posts_per_user = 0

    db.commit()
    return stats


def get_community_statistics(
    db: Session, community_id: int, start_date: date, end_date: date
):
    return (
        db.query(models.CommunityStatistics)
        .filter(
            models.CommunityStatistics.community_id == community_id,
            models.CommunityStatistics.date.between(start_date, end_date),
        )
        .all()
    )


# أضف هذه النقاط النهائية


@router.get(
    "/{community_id}/statistics", response_model=List[schemas.CommunityStatistics]
)
def get_community_statistics_endpoint(
    community_id: int,
    start_date: date,
    end_date: date,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(oauth2.get_current_user),
):
    community_member = (
        db.query(models.CommunityMember)
        .filter(
            models.CommunityMember.community_id == community_id,
            models.CommunityMember.user_id == current_user.id,
        )
        .first()
    )
    if not community_member:
        raise HTTPException(
            status_code=403, detail="You are not a member of this community"
        )

    stats = get_community_statistics(db, community_id, start_date, end_date)
    return stats


@router.post(
    "/{community_id}/update-statistics", response_model=schemas.CommunityStatistics
)
def update_community_statistics_endpoint(
    community_id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(oauth2.get_current_user),
):
    community_member = (
        db.query(models.CommunityMember)
        .filter(
            models.CommunityMember.community_id == community_id,
            models.CommunityMember.user_id == current_user.id,
            models.CommunityMember.role.in_(
                [models.CommunityRole.ADMIN, models.CommunityRole.MODERATOR]
            ),
        )
        .first()
    )
    if not community_member:
        raise HTTPException(
            status_code=403, detail="You don't have permission to update statistics"
        )

    stats = update_community_statistics(db, community_id)
    return stats


@router.get("/{community_id}/statistics-chart", response_class=HTMLResponse)
async def get_community_statistics_chart(
    community_id: int,
    start_date: date,
    end_date: date,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(oauth2.get_current_user),
):
    community_member = (
        db.query(models.CommunityMember)
        .filter(
            models.CommunityMember.community_id == community_id,
            models.CommunityMember.user_id == current_user.id,
        )
        .first()
    )
    if not community_member:
        raise HTTPException(
            status_code=403, detail="You are not a member of this community"
        )

    stats = get_community_statistics(db, community_id, start_date, end_date)

    # Prepare data for Chart.js
    labels = [stat.date.strftime("%Y-%m-%d") for stat in stats]
    member_counts = [stat.member_count for stat in stats]
    post_counts = [stat.post_count for stat in stats]
    comment_counts = [stat.comment_count for stat in stats]
    active_users = [stat.active_users for stat in stats]
    total_reactions = [stat.total_reactions for stat in stats]
    average_posts = [stat.average_posts_per_user for stat in stats]

    html_content = f"""
    <html>
        <head>
            <title>Community Statistics</title>
            <script src="https://cdn.jsdelivr.net/npm/chart.js"></script>
        </head>
        <body>
            <canvas id="communityStatsChart" width="800" height="400"></canvas>
            <script>
                var ctx = document.getElementById('communityStatsChart').getContext('2d');
                var chart = new Chart(ctx, {{
                    type: 'line',
                    data: {{
                        labels: {labels},
                        datasets: [
                            {{
                                label: 'Member Count',
                                data: {member_counts},
                                borderColor: 'rgb(75, 192, 192)',
                                tension: 0.1
                            }},
                            {{
                                label: 'Post Count',
                                data: {post_counts},
                                borderColor: 'rgb(255, 99, 132)',
                                tension: 0.1
                            }},
                            {{
                                label: 'Comment Count',
                                data: {comment_counts},
                                borderColor: 'rgb(54, 162, 235)',
                                tension: 0.1
                            }},
                            {{
                                label: 'Active Users',
                                data: {active_users},
                                borderColor: 'rgb(255, 206, 86)',
                                tension: 0.1
                            }},
                            {{
                                label: 'Total Reactions',
                                data: {total_reactions},
                                borderColor: 'rgb(153, 102, 255)',
                                tension: 0.1
                            }},
                            {{
                                label: 'Average Posts per User',
                                data: {average_posts},
                                borderColor: 'rgb(255, 159, 64)',
                                tension: 0.1
                            }}
                        ]
                    }},
                    options: {{
                        responsive: true,
                        title: {{
                            display: true,
                            text: 'Community Statistics'
                        }}
                    }}
                }});
            </script>
        </body>
    </html>
    """
    return HTMLResponse(content=html_content)


@router.get("/{community_id}/export-statistics")
async def export_community_statistics(
    community_id: int,
    start_date: date,
    end_date: date,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(oauth2.get_current_user),
):
    community_member = (
        db.query(models.CommunityMember)
        .filter(
            models.CommunityMember.community_id == community_id,
            models.CommunityMember.user_id == current_user.id,
            models.CommunityMember.role.in_(
                [models.CommunityRole.ADMIN, models.CommunityRole.MODERATOR]
            ),
        )
        .first()
    )
    if not community_member:
        raise HTTPException(
            status_code=403, detail="You don't have permission to export statistics"
        )

    stats = get_community_statistics(db, community_id, start_date, end_date)

    output = StringIO()
    writer = csv.writer(output)
    writer.writerow(
        [
            "Date",
            "Member Count",
            "Post Count",
            "Comment Count",
            "Active Users",
            "Total Reactions",
            "Average Posts per User",
        ]
    )
    for stat in stats:
        writer.writerow(
            [
                stat.date,
                stat.member_count,
                stat.post_count,
                stat.comment_count,
                stat.active_users,
                stat.total_reactions,
                stat.average_posts_per_user,
            ]
        )

    output.seek(0)
    return StreamingResponse(
        iter([output.getvalue()]),
        media_type="text/csv",
        headers={
            "Content-Disposition": f"attachment; filename=community_{community_id}_statistics.csv"
        },
    )


@router.post("/categories/", response_model=schemas.Category)
def create_category(
    category: schemas.CategoryCreate,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(oauth2.get_current_user),
):
    if not current_user.role == "ADMIN":
        raise HTTPException(status_code=403, detail="Only admins can create categories")
    db_category = models.Category(**category.dict())
    db.add(db_category)
    db.commit()
    db.refresh(db_category)
    return db_category


@router.get("/categories/", response_model=List[schemas.Category])
def get_categories(db: Session = Depends(get_db)):
    categories = db.query(models.Category).all()
    return categories


@router.post("/tags/", response_model=schemas.Tag)
def create_tag(
    tag: schemas.TagCreate,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(oauth2.get_current_user),
):
    if not current_user.role == "ADMIN":
        raise HTTPException(status_code=403, detail="Only admins can create tags")
    db_tag = models.Tag(**tag.dict())
    db.add(db_tag)
    db.commit()
    db.refresh(db_tag)
    return db_tag


@router.get("/tags/", response_model=List[schemas.Tag])
def get_tags(db: Session = Depends(get_db)):
    tags = db.query(models.Tag).all()
    return tags


@router.post("/{community_id}/join-request")
def request_to_join(community_id: int, user_id: int, db: Session = Depends(get_db)):
    community = (
        db.query(models.Community).filter(models.Community.id == community_id).first()
    )
    if not community:
        raise HTTPException(status_code=404, detail="Community not found")
    if not community.is_private and not community.requires_approval:
        # Автоматическое присоединение к открытому сообществу
        # Реализуйте логику присоединения здесь
        return {"message": "Joined community successfully"}
    else:
        # Создание запроса на присоединение
        join_request = models.CommunityJoinRequest(
            community_id=community_id, user_id=user_id
        )
        db.add(join_request)
        db.commit()
        return {"message": "Join request submitted successfully"}


class CommunityNotificationHandler:
    def __init__(self, db: Session, background_tasks: BackgroundTasks):
        self.db = db
        self.background_tasks = background_tasks
        self.notification_service = NotificationService(db, background_tasks)

    async def handle_community_invitation(self, invitation: models.CommunityInvitation):
        """معالجة إشعارات دعوات المجتمع"""
        await self.notification_service.create_notification(
            user_id=invitation.invitee_id,
            content=f"{invitation.inviter.username} دعاك للانضمام إلى مجتمع {invitation.community.name}",
            notification_type="community_invitation",
            priority=models.NotificationPriority.MEDIUM,
            category=models.NotificationCategory.COMMUNITY,
            link=f"/community/{invitation.community_id}",
            metadata={
                "invitation_id": invitation.id,
                "community_id": invitation.community_id,
                "community_name": invitation.community.name,
                "inviter_id": invitation.inviter_id,
            },
        )

    async def handle_role_change(self, member: models.CommunityMember, old_role: str):
        """معالجة إشعارات تغيير الأدوار في المجتمع"""
        await self.notification_service.create_notification(
            user_id=member.user_id,
            content=f"تم تغيير دورك في مجتمع {member.community.name} من {old_role} إلى {member.role}",
            notification_type="role_change",
            priority=models.NotificationPriority.HIGH,
            category=models.NotificationCategory.COMMUNITY,
            link=f"/community/{member.community_id}",
        )
