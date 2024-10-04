from fastapi import APIRouter, Depends, HTTPException, status, Query, Request, Body
from sqlalchemy.orm import Session, joinedload
from typing import List, Union
from .. import models, schemas, oauth2
from ..database import get_db
import logging

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
    new_community = models.Community(owner_id=current_user.id, **community.dict())
    new_community.members.append(current_user)
    db.add(new_community)
    db.commit()
    db.refresh(new_community)
    return schemas.CommunityOut.from_orm(new_community)


@router.get("/", response_model=List[schemas.CommunityOut])
def get_communities(
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
    return [schemas.CommunityOut.from_orm(community) for community in communities]


@router.get("/{id}", response_model=schemas.CommunityOut)
def get_community(
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
    community_query.update(
        updated_community.dict(exclude_unset=True), synchronize_session=False
    )
    db.commit()
    return schemas.CommunityOut.from_orm(community_query.first())


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


@router.post(
    "/{community_id}/posts",
    status_code=status.HTTP_201_CREATED,
    response_model=schemas.PostOut,
)
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
    return Response(status_code=204)
