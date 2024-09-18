from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.orm import Session
from typing import List, Optional
from .. import models, schemas, oauth2
from ..database import get_db

router = APIRouter(prefix="/communities", tags=["Communities"])


@router.post(
    "/", status_code=status.HTTP_201_CREATED, response_model=schemas.CommunityOut
)
def create_community(
    community: schemas.CommunityCreate,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(oauth2.get_current_user),
):
    """
    Create a new community.
    """
    existing_community = (
        db.query(models.Community)
        .filter(models.Community.name == community.name)
        .first()
    )
    if existing_community:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="Community already exists"
        )

    new_community = models.Community(owner_id=current_user.id, **community.model_dump())
    db.add(new_community)
    db.commit()
    db.refresh(new_community)
    return schemas.CommunityOut(
        **new_community.__dict__,
        owner=schemas.UserOut.model_validate(new_community.owner),
        member_count=len(new_community.members),
    )


@router.get("/", response_model=schemas.CommunityList)
def get_communities(
    db: Session = Depends(get_db),
    current_user: models.User = Depends(oauth2.get_current_user),
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=100),
    search: Optional[str] = Query(None, min_length=3),
):
    """
    Get all communities with pagination and optional search.
    """
    query = db.query(models.Community)
    if search:
        query = query.filter(models.Community.name.ilike(f"%{search}%"))

    total = query.count()
    communities = query.offset(skip).limit(limit).all()

    community_list = [
        schemas.CommunityOut(
            **community.__dict__,
            owner=schemas.UserOut.model_validate(community.owner),
            member_count=len(community.members),
        )
        for community in communities
    ]

    return schemas.CommunityList(communities=community_list, total=total)


@router.get("/{community_id}", response_model=schemas.CommunityOut)
def get_community(
    community_id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(oauth2.get_current_user),
):
    """
    Get details of a specific community.
    """
    community = (
        db.query(models.Community).filter(models.Community.id == community_id).first()
    )
    if not community:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Community not found"
        )
    return schemas.CommunityOut(
        **community.__dict__,
        owner=schemas.UserOut.model_validate(community.owner),
        member_count=len(community.members),
    )


@router.put("/{community_id}", response_model=schemas.CommunityOut)
def update_community(
    community_id: int,
    community_update: schemas.CommunityUpdate,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(oauth2.get_current_user),
):
    """
    Update a community. Only the owner can update the community.
    """
    community_query = db.query(models.Community).filter(
        models.Community.id == community_id
    )
    community = community_query.first()
    if not community:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Community not found"
        )
    if community.owner_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Not authorized to perform requested action",
        )

    update_data = community_update.model_dump(exclude_unset=True)
    community_query.update(update_data, synchronize_session=False)
    db.commit()
    db.refresh(community)
    return schemas.CommunityOut(
        **community.__dict__,
        owner=schemas.UserOut.model_validate(community.owner),
        member_count=len(community.members),
    )


@router.delete("/{community_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_community(
    community_id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(oauth2.get_current_user),
):
    """
    Delete a community. Only the owner can delete the community.
    """
    community_query = db.query(models.Community).filter(
        models.Community.id == community_id
    )
    community = community_query.first()
    if not community:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Community not found"
        )
    if community.owner_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Not authorized to perform requested action",
        )

    community_query.delete(synchronize_session=False)
    db.commit()
    return {"message": "Community deleted successfully"}


@router.post("/{community_id}/join", status_code=status.HTTP_200_OK)
def join_community(
    community_id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(oauth2.get_current_user),
):
    """
    Join a community.
    """
    community = (
        db.query(models.Community).filter(models.Community.id == community_id).first()
    )
    if not community:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Community not found"
        )

    if current_user.id in [member.id for member in community.members]:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="User is already a member of this community",
        )

    community.members.append(current_user)
    db.commit()
    return {"message": "Joined the community successfully"}


@router.post("/{community_id}/leave", status_code=status.HTTP_200_OK)
def leave_community(
    community_id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(oauth2.get_current_user),
):
    """
    Leave a community.
    """
    community = (
        db.query(models.Community).filter(models.Community.id == community_id).first()
    )
    if not community:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Community not found"
        )

    if current_user.id not in [member.id for member in community.members]:
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
    return {"message": "Left the community successfully"}
