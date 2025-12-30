"""Sticker router for packs/categories/reports and media upload validation.

Auth required; enforces image validation and uses services/models for persistence.
Uploads go through PIL/emoji checks; DB writes scoped via FastAPI dependencies.
"""

import io
import os
from typing import List

import emoji

# External libraries for image processing and emojis
from PIL import Image
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.modules.stickers import models as sticker_models
from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status

# Import project modules
from .. import models, oauth2, schemas

router = APIRouter(prefix="/stickers", tags=["Stickers"])

# Directory where sticker images will be stored
UPLOAD_DIRECTORY = "static/stickers"


def _is_admin(user: models.User) -> bool:
    role = getattr(user, "role", "")
    if hasattr(role, "value"):
        role = role.value
    return str(role).lower() == "admin" or getattr(user, "is_admin", False)


# ------------------------------------------------------------------
#                         Endpoints
# ------------------------------------------------------------------


@router.post(
    "/pack", status_code=status.HTTP_201_CREATED, response_model=schemas.StickerPack
)
def create_sticker_pack(
    pack: schemas.StickerPackCreate,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(oauth2.get_current_user),
):
    """
    Create a new sticker pack.

    - **pack**: Sticker pack data (name, etc.)
    - **current_user**: Authenticated user creating the pack

    Returns the created sticker pack.
    """
    existing = (
        db.query(sticker_models.StickerPack)
        .filter(
            func.lower(sticker_models.StickerPack.name) == pack.name.lower(),
            sticker_models.StickerPack.creator_id == current_user.id,
        )
        .first()
    )
    if existing:
        raise HTTPException(
            status_code=409, detail="Sticker pack with this name already exists"
        )

    new_pack = sticker_models.StickerPack(name=pack.name, creator_id=current_user.id)
    db.add(new_pack)
    db.commit()
    db.refresh(new_pack)
    return new_pack


@router.post("/", status_code=status.HTTP_201_CREATED, response_model=schemas.Sticker)
async def create_sticker(
    sticker: schemas.StickerCreate,
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    current_user: models.User = Depends(oauth2.get_current_user),
):
    """
    Create a new sticker within a sticker pack.

    This endpoint processes the uploaded image, validates its format,
    saves it to the UPLOAD_DIRECTORY, and creates a new sticker record.

    - **sticker**: Sticker data (name, pack_id, category_ids, etc.)
    - **file**: Uploaded image file (PNG or WEBP only)

    Returns the created sticker.
    """
    # Verify that the sticker pack exists and belongs to the current user
    pack = (
        db.query(sticker_models.StickerPack)
        .filter(sticker_models.StickerPack.id == sticker.pack_id)
        .first()
    )
    if not pack or pack.creator_id != current_user.id:
        raise HTTPException(
            status_code=404,
            detail="Sticker pack not found or you don't have permission",
        )

    try:
        # Read and open the image from the uploaded file
        image_bytes = await file.read()
        image = Image.open(io.BytesIO(image_bytes))

        # Validate image format (only PNG and WEBP allowed)
        if image.format not in ["PNG", "WEBP"]:
            raise HTTPException(
                status_code=400, detail="Only PNG and WEBP formats are allowed"
            )

        # Ensure the upload directory exists
        if not os.path.exists(UPLOAD_DIRECTORY):
            os.makedirs(UPLOAD_DIRECTORY)

        # Save the image file
        image_path = f"{UPLOAD_DIRECTORY}/{file.filename}"
        image.save(image_path)

        # Create the sticker record with image URL and associated pack
        new_sticker = sticker_models.Sticker(
            name=sticker.name, image_url=image_path, pack_id=sticker.pack_id
        )

        # Retrieve and assign sticker categories based on provided IDs
        categories = (
            db.query(sticker_models.StickerCategory)
            .filter(sticker_models.StickerCategory.id.in_(sticker.category_ids))
            .all()
        )
        new_sticker.categories = categories

        db.add(new_sticker)
        db.commit()
        db.refresh(new_sticker)
        return new_sticker

    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/pack/{pack_id}", response_model=schemas.StickerPackWithStickers)
def get_sticker_pack(pack_id: int, db: Session = Depends(get_db)):
    """Endpoint: get_sticker_pack."""
    pack = (
        db.query(sticker_models.StickerPack)
        .filter(sticker_models.StickerPack.id == pack_id)
        .first()
    )
    if not pack:
        raise HTTPException(status_code=404, detail="Sticker pack not found")
    return pack


@router.get("/", response_model=List[schemas.Sticker])
def get_stickers(approved_only: bool = True, db: Session = Depends(get_db)):
    """Endpoint: get_stickers."""
    query = db.query(sticker_models.Sticker)
    if approved_only:
        query = query.filter(sticker_models.Sticker.approved.is_(True))
    stickers = query.all()
    return stickers


@router.get("/search")
def search_stickers(query: str, db: Session = Depends(get_db)):
    """Endpoint: search_stickers."""
    stickers = (
        db.query(sticker_models.Sticker)
        .filter(sticker_models.Sticker.name.ilike(f"%{query}%"))
        .all()
    )
    return stickers


@router.get("/emojis")
def get_emojis():
    """Endpoint: get_emojis."""
    return {"emojis": emoji.EMOJI_ALIAS_UNICODE_ENGLISH}


@router.put("/{sticker_id}/approve")
def approve_sticker(
    sticker_id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(oauth2.get_current_user),
):
    """
    Approve a sticker.

    Only users with the ADMIN role are allowed to approve stickers.

    - **sticker_id**: ID of the sticker to approve

    Returns a success message upon approval.
    """
    if not _is_admin(current_user):
        raise HTTPException(status_code=403, detail="Only admins can approve stickers")

    sticker = (
        db.query(sticker_models.Sticker)
        .filter(sticker_models.Sticker.id == sticker_id)
        .first()
    )
    if not sticker:
        raise HTTPException(status_code=404, detail="Sticker not found")

    sticker.approved = True
    db.commit()
    return {"message": "Sticker approved successfully"}


@router.post(
    "/category",
    status_code=status.HTTP_201_CREATED,
    response_model=schemas.StickerCategory,
)
def create_sticker_category(
    category: schemas.StickerCategoryCreate,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(oauth2.get_current_user),
):
    """
    Create a new sticker category.

    Only ADMIN users can create sticker categories.

    - **category**: Category data (e.g., name)

    Returns the created sticker category.
    """
    if not _is_admin(current_user):
        raise HTTPException(
            status_code=403, detail="Only admins can create sticker categories"
        )

    existing = (
        db.query(sticker_models.StickerCategory)
        .filter(
            func.lower(sticker_models.StickerCategory.name) == category.name.lower()
        )
        .first()
    )
    if existing:
        raise HTTPException(
            status_code=409, detail="Sticker category with this name already exists"
        )

    new_category = sticker_models.StickerCategory(name=category.name)
    db.add(new_category)
    db.commit()
    db.refresh(new_category)
    return new_category


@router.post(
    "/report", status_code=status.HTTP_201_CREATED, response_model=schemas.StickerReport
)
def report_sticker(
    report: schemas.StickerReportCreate,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(oauth2.get_current_user),
):
    """
    Report a sticker for a specified reason.

    - **report**: Report data including sticker_id and reason

    Returns the created sticker report.
    """
    sticker = (
        db.query(sticker_models.Sticker)
        .filter(sticker_models.Sticker.id == report.sticker_id)
        .first()
    )
    if not sticker:
        raise HTTPException(status_code=404, detail="Sticker not found")

    existing = (
        db.query(sticker_models.StickerReport)
        .filter(
            sticker_models.StickerReport.sticker_id == report.sticker_id,
            sticker_models.StickerReport.reporter_id == current_user.id,
        )
        .first()
    )
    if existing:
        raise HTTPException(status_code=409, detail="You already reported this sticker")

    new_report = sticker_models.StickerReport(
        sticker_id=report.sticker_id, reporter_id=current_user.id, reason=report.reason
    )
    db.add(new_report)
    db.commit()
    db.refresh(new_report)
    return new_report


@router.get("/reports", response_model=List[schemas.StickerReport])
def get_sticker_reports(
    db: Session = Depends(get_db),
    current_user: models.User = Depends(oauth2.get_current_user),
):
    """
    Retrieve all sticker reports.

    Only ADMIN users can view sticker reports.

    Returns a list of reported stickers.
    """
    if not _is_admin(current_user):
        raise HTTPException(
            status_code=403, detail="Only admins can view sticker reports"
        )

    reports = db.query(sticker_models.StickerReport).all()
    return reports


@router.get("/categories", response_model=List[schemas.StickerCategory])
def get_sticker_categories(db: Session = Depends(get_db)):
    """Endpoint: get_sticker_categories."""
    categories = db.query(sticker_models.StickerCategory).all()
    return categories


@router.get("/category/{category_id}", response_model=List[schemas.Sticker])
def get_stickers_by_category(category_id: int, db: Session = Depends(get_db)):
    """Endpoint: get_stickers_by_category."""
    stickers = (
        db.query(sticker_models.Sticker)
        .filter(sticker_models.Sticker.categories.any(id=category_id))
        .all()
    )
    return stickers


@router.put("/{sticker_id}/disable")
def disable_sticker(
    sticker_id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(oauth2.get_current_user),
):
    """Disable (hide) a sticker from listings."""
    if not _is_admin(current_user):
        raise HTTPException(status_code=403, detail="Only admins can disable stickers")

    sticker = (
        db.query(sticker_models.Sticker)
        .filter(sticker_models.Sticker.id == sticker_id)
        .first()
    )
    if not sticker:
        raise HTTPException(status_code=404, detail="Sticker not found")

    sticker.approved = False
    db.commit()
    return {"message": "Sticker disabled"}


@router.put("/{sticker_id}/enable")
def enable_sticker(
    sticker_id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(oauth2.get_current_user),
):
    """Re-enable a sticker."""
    if not _is_admin(current_user):
        raise HTTPException(status_code=403, detail="Only admins can enable stickers")

    sticker = (
        db.query(sticker_models.Sticker)
        .filter(sticker_models.Sticker.id == sticker_id)
        .first()
    )
    if not sticker:
        raise HTTPException(status_code=404, detail="Sticker not found")
    sticker.approved = True
    db.commit()
    return {"message": "Sticker enabled"}
