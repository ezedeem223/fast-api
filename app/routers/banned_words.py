"""
Banned Words Management Router
يوفر نقاط النهاية لإدارة الكلمات المحظورة في النظام
"""

from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.orm import Session
from sqlalchemy import func
from typing import List, Optional
from .. import models, schemas, oauth2, utils
from ..database import get_db
from ..cache import cache

router = APIRouter(prefix="/banned-words", tags=["Banned Words"])


async def check_admin(current_user: models.User = Depends(oauth2.get_current_user)):
    """التحقق من صلاحيات المسؤول"""
    if not await utils.is_admin(current_user):
        raise HTTPException(
            status_code=403, detail="فقط المسؤولون يمكنهم تنفيذ هذا الإجراء"
        )
    return current_user


@router.post(
    "/", status_code=status.HTTP_201_CREATED, response_model=schemas.BannedWordOut
)
async def add_banned_word(
    word: schemas.BannedWordCreate,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(check_admin),
):
    """
    إضافة كلمة محظورة جديدة

    Parameters:
        word: الكلمة المراد حظرها
        db: جلسة قاعدة البيانات
        current_user: المستخدم الحالي (يجب أن يكون مسؤولاً)

    Returns:
        BannedWordOut: معلومات الكلمة المحظورة
    """
    # التحقق من عدم وجود الكلمة مسبقاً
    existing_word = (
        db.query(models.BannedWord)
        .filter(func.lower(models.BannedWord.word) == word.word.lower())
        .first()
    )
    if existing_word:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="هذه الكلمة محظورة بالفعل"
        )

    # إنشاء كلمة محظورة جديدة
    new_banned_word = models.BannedWord(**word.dict(), created_by=current_user.id)
    db.add(new_banned_word)
    db.commit()
    db.refresh(new_banned_word)

    # تحديث إحصائيات الحظر
    utils.update_ban_statistics(db, "word", "إضافة كلمة محظورة", 1.0)

    # تسجيل الإجراء
    utils.log_admin_action(db, current_user.id, "add_banned_word", {"word": word.word})

    return new_banned_word


@router.get("/", response_model=schemas.BannedWordListOut)
@cache(expire=300)  # تخزين مؤقت لمدة 5 دقائق
async def get_banned_words(
    db: Session = Depends(get_db),
    current_user: models.User = Depends(check_admin),
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=1000),
    search: Optional[str] = None,
    sort_by: Optional[str] = Query(
        "word", description="الترتيب حسب 'word' أو 'created_at'"
    ),
    sort_order: Optional[str] = Query(
        "asc", description="ترتيب تصاعدي 'asc' أو تنازلي 'desc'"
    ),
):
    """
    الحصول على قائمة الكلمات المحظورة

    Parameters:
        db: جلسة قاعدة البيانات
        current_user: المستخدم الحالي (يجب أن يكون مسؤولاً)
        skip: عدد النتائج المراد تخطيها
        limit: عدد النتائج المراد عرضها
        search: نص البحث
        sort_by: حقل الترتيب
        sort_order: اتجاه الترتيب
    """
    query = db.query(models.BannedWord)

    # تطبيق البحث
    if search:
        query = query.filter(models.BannedWord.word.ilike(f"%{search}%"))

    # تطبيق الترتيب
    if sort_by == "word":
        query = query.order_by(
            models.BannedWord.word.asc()
            if sort_order == "asc"
            else models.BannedWord.word.desc()
        )
    elif sort_by == "created_at":
        query = query.order_by(
            models.BannedWord.created_at.asc()
            if sort_order == "asc"
            else models.BannedWord.created_at.desc()
        )

    total = query.count()
    words = query.offset(skip).limit(limit).all()

    return {"total": total, "words": words}


@router.delete("/{word_id}", status_code=status.HTTP_204_NO_CONTENT)
async def remove_banned_word(
    word_id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(check_admin),
):
    """
    إزالة كلمة محظورة

    Parameters:
        word_id: معرف الكلمة المحظورة
        db: جلسة قاعدة البيانات
        current_user: المستخدم الحالي (يجب أن يكون مسؤولاً)
    """
    word = db.query(models.BannedWord).filter(models.BannedWord.id == word_id).first()
    if not word:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="الكلمة المحظورة غير موجودة"
        )

    db.delete(word)
    db.commit()

    utils.log_admin_action(
        db, current_user.id, "remove_banned_word", {"word_id": word_id}
    )

    return {"message": "تمت إزالة الكلمة المحظورة بنجاح"}


@router.put("/{word_id}", response_model=schemas.BannedWordOut)
async def update_banned_word(
    word_id: int,
    word_update: schemas.BannedWordUpdate,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(check_admin),
):
    """
    تحديث كلمة محظورة

    Parameters:
        word_id: معرف الكلمة المحظورة
        word_update: بيانات التحديث
        db: جلسة قاعدة البيانات
        current_user: المستخدم الحالي (يجب أن يكون مسؤولاً)
    """
    word = db.query(models.BannedWord).filter(models.BannedWord.id == word_id).first()
    if not word:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="الكلمة المحظورة غير موجودة"
        )

    for key, value in word_update.dict(exclude_unset=True).items():
        setattr(word, key, value)

    db.commit()
    db.refresh(word)

    utils.log_admin_action(
        db,
        current_user.id,
        "update_banned_word",
        {"word_id": word_id, "updates": word_update.dict(exclude_unset=True)},
    )

    return word


@router.post("/bulk", status_code=status.HTTP_201_CREATED)
async def add_banned_words_bulk(
    words: List[schemas.BannedWordCreate],
    db: Session = Depends(get_db),
    current_user: models.User = Depends(check_admin),
):
    """
    إضافة مجموعة من الكلمات المحظورة دفعة واحدة

    Parameters:
        words: قائمة الكلمات المراد حظرها
        db: جلسة قاعدة البيانات
        current_user: المستخدم الحالي (يجب أن يكون مسؤولاً)
    """
    new_words = [
        models.BannedWord(**word.dict(), created_by=current_user.id) for word in words
    ]
    db.add_all(new_words)
    db.commit()

    utils.log_admin_action(
        db, current_user.id, "add_banned_words_bulk", {"count": len(new_words)}
    )

    return {
        "message": f"تمت إضافة {len(new_words)} كلمة محظورة بنجاح",
        "added_words": len(new_words),
    }
