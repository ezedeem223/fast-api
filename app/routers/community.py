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
    # Check if the community exists first
    community = (
        db.query(models.Community).filter(models.Community.id == community_id).first()
    )
    if not community:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Community with id: {community_id} not found",
        )

    # Rest of the function remains the same
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


@router.get("/invitations", response_model=List[schemas.CommunityInvitationOut])
async def get_user_invitations(
    db: Session = Depends(get_db),
    current_user: models.User = Depends(oauth2.get_current_user),
):
    try:
        invitations = (
            db.query(models.CommunityInvitation)
            .filter(
                models.CommunityInvitation.invitee_id == current_user.id,
                models.CommunityInvitation.status == "pending",
            )
            .all()
        )

        # Log the invitations for debugging
        logger.debug(f"Fetched invitations: {invitations}")

        return [schemas.CommunityInvitationOut.from_orm(inv) for inv in invitations]
    except Exception as e:
        logger.error(f"Error in get_user_invitations: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"An error occurred while fetching invitations: {str(e)}",
        )


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


# @router.get("/{community_id}/members", response_model=List[schemas.UserOut])
# def get_community_members(
#     community_id: int,
#     db: Session = Depends(get_db),
#     current_user: models.User = Depends(oauth2.get_current_user),
#     skip: int = Query(0, ge=0),
#     limit: int = Query(20, ge=1, le=100),
# ):
#     community = (
#         db.query(models.Community).filter(models.Community.id == community_id).first()
#     )
#     if not community:
#         raise HTTPException(
#             status_code=status.HTTP_404_NOT_FOUND,
#             detail=f"Community with id: {community_id} was not found",
#         )

#     members = community.members[skip : skip + limit]
#     return [schemas.UserOut.from_orm(member) for member in members]


# @router.post("/{community_id}/remove-member/{user_id}", status_code=status.HTTP_200_OK)
# def remove_community_member(
#     community_id: int,
#     user_id: int,
#     db: Session = Depends(get_db),
#     current_user: models.User = Depends(oauth2.get_current_user),
# ):
#     community = (
#         db.query(models.Community).filter(models.Community.id == community_id).first()
#     )
#     if not community:
#         raise HTTPException(
#             status_code=status.HTTP_404_NOT_FOUND,
#             detail=f"Community with id: {community_id} was not found",
#         )

#     if community.owner_id != current_user.id:
#         raise HTTPException(
#             status_code=status.HTTP_403_FORBIDDEN,
#             detail="Only the community owner can remove members",
#         )

#     user_to_remove = db.query(models.User).filter(models.User.id == user_id).first()
#     if not user_to_remove:
#         raise HTTPException(
#             status_code=status.HTTP_404_NOT_FOUND,
#             detail=f"User with id: {user_id} was not found",
#         )

#     if user_to_remove not in community.members:
#         raise HTTPException(
#             status_code=status.HTTP_400_BAD_REQUEST,
#             detail="User is not a member of this community",
#         )

#     if user_to_remove.id == community.owner_id:
#         raise HTTPException(
#             status_code=status.HTTP_400_BAD_REQUEST,
#             detail="Cannot remove the community owner",
#         )

#     community.members.remove(user_to_remove)
#     db.commit()
#     return {"message": f"User {user_id} has been removed from the community"}


# @router.get("/{community_id}/stats", response_model=schemas.CommunityStats)
# def get_community_stats(
#     community_id: int,
#     db: Session = Depends(get_db),
#     current_user: models.User = Depends(oauth2.get_current_user),
# ):
#     community = (
#         db.query(models.Community).filter(models.Community.id == community_id).first()
#     )
#     if not community:
#         raise HTTPException(
#             status_code=status.HTTP_404_NOT_FOUND,
#             detail=f"Community with id: {community_id} was not found",
#         )

#     member_count = len(community.members)
#     post_count = (
#         db.query(models.Post).filter(models.Post.community_id == community_id).count()
#     )
#     reel_count = (
#         db.query(models.Reel).filter(models.Reel.community_id == community_id).count()
#     )
#     article_count = (
#         db.query(models.Article)
#         .filter(models.Article.community_id == community_id)
#         .count()
#     )

#     return schemas.CommunityStats(
#         member_count=member_count,
#         post_count=post_count,
#         reel_count=reel_count,
#         article_count=article_count,
#     )


# @router.put(
#     "/{community_id}/change-owner/{new_owner_id}", response_model=schemas.CommunityOut
# )
# def change_community_owner(
#     community_id: int,
#     new_owner_id: int,
#     db: Session = Depends(get_db),
#     current_user: models.User = Depends(oauth2.get_current_user),
# ):
#     community = (
#         db.query(models.Community).filter(models.Community.id == community_id).first()
#     )
#     if not community:
#         raise HTTPException(
#             status_code=status.HTTP_404_NOT_FOUND,
#             detail=f"Community with id: {community_id} was not found",
#         )

#     if community.owner_id != current_user.id:
#         raise HTTPException(
#             status_code=status.HTTP_403_FORBIDDEN,
#             detail="Only the current owner can transfer ownership",
#         )

#     new_owner = db.query(models.User).filter(models.User.id == new_owner_id).first()
#     if not new_owner:
#         raise HTTPException(
#             status_code=status.HTTP_404_NOT_FOUND,
#             detail=f"User with id: {new_owner_id} was not found",
#         )

#     if new_owner not in community.members:
#         raise HTTPException(
#             status_code=status.HTTP_400_BAD_REQUEST,
#             detail="New owner must be a member of the community",
#         )

#     community.owner_id = new_owner_id
#     db.commit()
#     db.refresh(community)
#     return schemas.CommunityOut.from_orm(community)


# # إضافة المزيد من الوظائف حسب الحاجة...
