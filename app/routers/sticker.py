from fastapi import APIRouter, Depends, HTTPException, status, File, UploadFile
from sqlalchemy.orm import Session
from .. import models, schemas, oauth2
from ..database import get_db
from typing import List
import emoji
from PIL import Image
import io
import os

router = APIRouter(prefix="/stickers", tags=["Stickers"])

UPLOAD_DIRECTORY = "static/stickers"


@router.post(
    "/pack", status_code=status.HTTP_201_CREATED, response_model=schemas.StickerPack
)
def create_sticker_pack(
    pack: schemas.StickerPackCreate,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(oauth2.get_current_user),
):
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
        image = Image.open(io.BytesIO(await file.read()))
        if image.format not in ["PNG", "WEBP"]:
            raise HTTPException(
                status_code=400, detail="Only PNG and WEBP formats are allowed"
            )

        if not os.path.exists(UPLOAD_DIRECTORY):
            os.makedirs(UPLOAD_DIRECTORY)

        image_path = f"{UPLOAD_DIRECTORY}/{file.filename}"
        image.save(image_path)

        new_sticker = models.Sticker(
            name=sticker.name, image_url=image_path, pack_id=sticker.pack_id
        )

        # Add categories to the sticker
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
    pack = db.query(models.StickerPack).filter(models.StickerPack.id == pack_id).first()
    if not pack:
        raise HTTPException(status_code=404, detail="Sticker pack not found")
    return pack


@router.get("/search")
def search_stickers(query: str, db: Session = Depends(get_db)):
    stickers = (
        db.query(models.Sticker).filter(models.Sticker.name.ilike(f"%{query}%")).all()
    )
    return stickers


@router.get("/emojis")
def get_emojis():
    return {"emojis": emoji.EMOJI_ALIAS_UNICODE_ENGLISH}


@router.put("/{sticker_id}/approve")
def approve_sticker(
    sticker_id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(oauth2.get_current_user),
):
    if not current_user.role == "ADMIN":
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
    if not current_user.role == "ADMIN":
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
    if not current_user.role == "ADMIN":
        raise HTTPException(
            status_code=403, detail="Only admins can view sticker reports"
        )

    reports = db.query(models.StickerReport).all()
    return reports


@router.get("/categories", response_model=List[schemas.StickerCategory])
def get_sticker_categories(db: Session = Depends(get_db)):
    categories = db.query(models.StickerCategory).all()
    return categories


@router.get("/category/{category_id}", response_model=List[schemas.Sticker])
def get_stickers_by_category(category_id: int, db: Session = Depends(get_db)):
    stickers = (
        db.query(models.Sticker)
        .filter(models.Sticker.categories.any(id=category_id))
        .all()
    )
    return stickers
