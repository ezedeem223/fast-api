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
    current_user: int = Depends(oauth2.get_current_user),
):
    if not community.name.strip():
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Community name cannot be empty",
        )
    new_community = models.Community(owner_id=current_user.id, **community.dict())
    new_community.members.append(current_user)
    db.add(new_community)
    db.commit()
    db.refresh(new_community)
    return new_community


@router.get("/", response_model=List[schemas.CommunityOut])
def get_communities(
    db: Session = Depends(get_db),
    current_user: int = Depends(oauth2.get_current_user),
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=100),
    search: Optional[str] = Query(None, min_length=3),
):
    query = db.query(models.Community)
    if search:
        query = query.filter(models.Community.name.ilike(f"%{search}%"))
    communities = query.offset(skip).limit(limit).all()
    return communities


@router.get("/{id}", response_model=schemas.CommunityOut)
def get_community(
    id: int,
    db: Session = Depends(get_db),
    current_user: int = Depends(oauth2.get_current_user),
):
    community = db.query(models.Community).filter(models.Community.id == id).first()
    if not community:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Community with id: {id} was not found",
        )
    return community


@router.put("/{id}", response_model=schemas.CommunityOut)
def update_community(
    id: int,
    updated_community: schemas.CommunityUpdate,
    db: Session = Depends(get_db),
    current_user: int = Depends(oauth2.get_current_user),
):
    community_query = db.query(models.Community).filter(models.Community.id == id)
    community = community_query.first()
    if community == None:
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
    return community_query.first()


@router.delete("/{id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_community(
    id: int,
    db: Session = Depends(get_db),
    current_user: int = Depends(oauth2.get_current_user),
):
    community_query = db.query(models.Community).filter(models.Community.id == id)
    community = community_query.first()
    if community == None:
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
    current_user: int = Depends(oauth2.get_current_user),
):
    community = db.query(models.Community).filter(models.Community.id == id).first()
    if not community:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Community with id: {id} was not found",
        )

    # Check if the user is already a member
    if any(member.id == current_user.id for member in community.members):
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
    current_user: int = Depends(oauth2.get_current_user),
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
    db.refresh(community)  # Add this line to refresh the session
    return {"message": "Left the community successfully"}
