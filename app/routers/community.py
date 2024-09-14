from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from typing import List
from .. import models, schemas, oauth2
from ..database import get_db

router = APIRouter(prefix="/communities", tags=["Communities"])


# إنشاء مجتمع جديد
@router.post(
    "/", status_code=status.HTTP_201_CREATED, response_model=schemas.CommunityOut
)
def create_community(
    community: schemas.CommunityCreate,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(oauth2.get_current_user),
):
    # التحقق إذا كان المجتمع موجود بالفعل
    existing_community = (
        db.query(models.Community)
        .filter(models.Community.name == community.name)
        .first()
    )
    if existing_community:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="Community already exists"
        )

    new_community = models.Community(owner_id=current_user.id, **community.dict())
    db.add(new_community)
    db.commit()
    db.refresh(new_community)
    return new_community


# الحصول على جميع المجتمعات
@router.get("/", response_model=List[schemas.CommunityOut])
def get_communities(
    db: Session = Depends(get_db),
    current_user: models.User = Depends(oauth2.get_current_user),
):
    communities = db.query(models.Community).all()
    return communities


# الانضمام إلى مجتمع
@router.post("/{community_id}/join", status_code=status.HTTP_200_OK)
def join_community(
    community_id: int,
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

    # التحقق إذا كان المستخدم عضوًا بالفعل
    if current_user.id in [member.id for member in community.members]:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="User is already a member of this community",
        )

    community.members.append(current_user)
    db.commit()
    return {"message": "Joined the community successfully"}


# مغادرة مجتمع
@router.post("/{community_id}/leave", status_code=status.HTTP_200_OK)
def leave_community(
    community_id: int,
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

    # التحقق إذا كان المستخدم عضوًا في المجتمع
    if current_user.id not in [member.id for member in community.members]:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="User is not a member of this community",
        )

    community.members.remove(current_user)
    db.commit()
    return {"message": "Left the community successfully"}
