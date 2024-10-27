from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from typing import List
from .. import models, schemas, oauth2
from ..database import get_db

router = APIRouter(prefix="/categories", tags=["Categories"])


@router.post(
    "/", status_code=status.HTTP_201_CREATED, response_model=schemas.PostCategory
)
def create_category(
    category: schemas.PostCategoryCreate,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(oauth2.get_current_user),
):
    """
    إنشاء تصنيف جديد

    Parameters:
        category: البيانات المطلوبة لإنشاء التصنيف
        db: جلسة قاعدة البيانات
        current_user: المستخدم الحالي

    Returns:
        schemas.PostCategory: التصنيف الذي تم إنشاؤه

    Raises:
        HTTPException: في حالة عدم وجود صلاحيات كافية
    """
    if not current_user.is_admin:
        raise HTTPException(status_code=403, detail="Only admins can create categories")

    new_category = models.PostCategory(**category.dict())
    db.add(new_category)
    db.commit()
    db.refresh(new_category)
    return new_category


@router.put("/{category_id}", response_model=schemas.PostCategory)
def update_category(
    category_id: int,
    category: schemas.PostCategoryCreate,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(oauth2.get_current_user),
):
    """
    تحديث تصنيف موجود

    Parameters:
        category_id: معرف التصنيف المراد تحديثه
        category: البيانات الجديدة للتصنيف
        db: جلسة قاعدة البيانات
        current_user: المستخدم الحالي

    Returns:
        schemas.PostCategory: التصنيف بعد التحديث

    Raises:
        HTTPException: في حالة عدم وجود التصنيف أو عدم وجود صلاحيات كافية
    """
    if not current_user.is_admin:
        raise HTTPException(status_code=403, detail="Only admins can update categories")

    db_category = (
        db.query(models.PostCategory)
        .filter(models.PostCategory.id == category_id)
        .first()
    )

    if not db_category:
        raise HTTPException(status_code=404, detail="Category not found")

    for key, value in category.dict().items():
        setattr(db_category, key, value)

    db.commit()
    db.refresh(db_category)
    return db_category


@router.delete("/{category_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_category(
    category_id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(oauth2.get_current_user),
):
    """
    حذف تصنيف

    Parameters:
        category_id: معرف التصنيف المراد حذفه
        db: جلسة قاعدة البيانات
        current_user: المستخدم الحالي

    Returns:
        dict: رسالة تأكيد الحذف

    Raises:
        HTTPException: في حالة عدم وجود التصنيف أو عدم وجود صلاحيات كافية
    """
    if not current_user.is_admin:
        raise HTTPException(status_code=403, detail="Only admins can delete categories")

    db_category = (
        db.query(models.PostCategory)
        .filter(models.PostCategory.id == category_id)
        .first()
    )

    if not db_category:
        raise HTTPException(status_code=404, detail="Category not found")

    db.delete(db_category)
    db.commit()
    return {"message": "Category deleted successfully"}


@router.get("/", response_model=List[schemas.PostCategory])
def get_categories(db: Session = Depends(get_db)):
    """
    الحصول على قائمة التصنيفات

    Parameters:
        db: جلسة قاعدة البيانات

    Returns:
        List[schemas.PostCategory]: قائمة بجميع التصنيفات الرئيسية
    """
    categories = (
        db.query(models.PostCategory)
        .filter(models.PostCategory.parent_id == None)
        .all()
    )
    return categories
