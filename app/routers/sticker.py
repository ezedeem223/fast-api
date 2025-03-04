from fastapi import APIRouter, Depends, HTTPException, status, File, UploadFile
from sqlalchemy.orm import Session
from typing import List
import os
import io

# External libraries for image processing and emojis
from PIL import Image
import emoji

# Import project modules
from .. import models, schemas, oauth2
from ..database import get_db

router = APIRouter(prefix="/stickers", tags=["Stickers"])

# Directory where sticker images will be stored
UPLOAD_DIRECTORY = "static/stickers"

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
    new_pack = models.StickerPack(name=pack.name, creator_id=current_user.id)
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
        db.query(models.StickerPack)
        .filter(models.StickerPack.id == sticker.pack_id)
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
        new_sticker = models.Sticker(
            name=sticker.name, image_url=image_path, pack_id=sticker.pack_id
        )

        # Retrieve and assign sticker categories based on provided IDs
        categories = (
            db.query(models.StickerCategory)
            .filter(models.StickerCategory.id.in_(sticker.category_ids))
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
    """
    Retrieve a sticker pack along with its stickers.

    - **pack_id**: ID of the sticker pack

    Returns the sticker pack if found.
    """
    pack = db.query(models.StickerPack).filter(models.StickerPack.id == pack_id).first()
    if not pack:
        raise HTTPException(status_code=404, detail="Sticker pack not found")
    return pack


@router.get("/", response_model=List[schemas.StickerOut])
def get_stickers(db: Session = Depends(get_db)):
    """
    Retrieve a list of all stickers.

    Returns all stickers from the database.
    """
    stickers = db.query(models.Sticker).all()
    return stickers


@router.get("/search")
def search_stickers(query: str, db: Session = Depends(get_db)):
    """
    Search for stickers by name.

    - **query**: Search keyword

    Returns a list of stickers matching the query.
    """
    stickers = (
        db.query(models.Sticker).filter(models.Sticker.name.ilike(f"%{query}%")).all()
    )
    return stickers


@router.get("/emojis")
def get_emojis():
    """
    Retrieve a dictionary of emojis.

    Uses the emoji library to return emoji aliases mapped to their unicode characters.
    """
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
    if current_user.role != "ADMIN":
        raise HTTPException(status_code=403, detail="Only admins can approve stickers")

    sticker = db.query(models.Sticker).filter(models.Sticker.id == sticker_id).first()
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
    if current_user.role != "ADMIN":
        raise HTTPException(
            status_code=403, detail="Only admins can create sticker categories"
        )

    new_category = models.StickerCategory(name=category.name)
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
        db.query(models.Sticker).filter(models.Sticker.id == report.sticker_id).first()
    )
    if not sticker:
        raise HTTPException(status_code=404, detail="Sticker not found")

    new_report = models.StickerReport(
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
    if current_user.role != "ADMIN":
        raise HTTPException(
            status_code=403, detail="Only admins can view sticker reports"
        )

    reports = db.query(models.StickerReport).all()
    return reports


@router.get("/categories", response_model=List[schemas.StickerCategory])
def get_sticker_categories(db: Session = Depends(get_db)):
    """
    Retrieve all sticker categories.

    Returns a list of all available sticker categories.
    """
    categories = db.query(models.StickerCategory).all()
    return categories


@router.get("/category/{category_id}", response_model=List[schemas.Sticker])
def get_stickers_by_category(category_id: int, db: Session = Depends(get_db)):
    """
    Retrieve all stickers that belong to a specific category.

    - **category_id**: ID of the sticker category

    Returns a list of stickers within the specified category.
    """
    stickers = (
        db.query(models.Sticker)
        .filter(models.Sticker.categories.any(id=category_id))
        .all()
    )
    return stickers
