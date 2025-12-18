"""Router for managing reels lifecycle and cleanup endpoints."""

from __future__ import annotations

from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from .. import models, schemas, oauth2
from app.core.database import get_db
from app.services.reels import ReelService

router = APIRouter(prefix="/reels", tags=["Reels"])


def get_reel_service(db: Session = Depends(get_db)) -> ReelService:
    return ReelService(db)


@router.post("/", response_model=schemas.ReelOut, status_code=status.HTTP_201_CREATED)
async def create_reel(
    payload: schemas.ReelCreate,
    service: ReelService = Depends(get_reel_service),
    current_user: models.User = Depends(oauth2.get_current_user),
):
    return service.create_reel(payload=payload, current_user=current_user)


@router.get("/active", response_model=List[schemas.ReelOut])
async def list_reels(
    community_id: Optional[int] = Query(default=None, ge=1),
    limit: int = Query(default=20, ge=1, le=100),
    include_expired: bool = False,
    service: ReelService = Depends(get_reel_service),
    current_user: models.User = Depends(oauth2.get_current_user),
):
    if include_expired and not current_user.is_admin:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Admin rights required to inspect expired reels")
    return service.list_reels(
        community_id=community_id,
        limit=limit,
        include_expired=include_expired,
    )


@router.post("/{reel_id}/view", response_model=schemas.ReelOut)
async def increment_reel_views(
    reel_id: int,
    service: ReelService = Depends(get_reel_service),
):
    return service.record_view(reel_id=reel_id)


@router.delete("/{reel_id}", status_code=status.HTTP_200_OK)
async def delete_reel(
    reel_id: int,
    service: ReelService = Depends(get_reel_service),
    current_user: models.User = Depends(oauth2.get_current_user),
):
    service.deactivate_reel(reel_id=reel_id, current_user=current_user)
    return {"status": "deleted"}
