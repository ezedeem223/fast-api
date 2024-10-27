from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from typing import List
from .. import models, schemas, oauth2
from ..database import get_db
from sqlalchemy import func

router = APIRouter(prefix="/hashtags", tags=["Hashtags"])


# CRUD Operations
@router.post("/", response_model=schemas.Hashtag)
def create_hashtag(hashtag: schemas.HashtagCreate, db: Session = Depends(get_db)):
    """
    إنشاء هاشتاج جديد

    Parameters:
        hashtag: نموذج إنشاء الهاشتاج
        db: جلسة قاعدة البيانات

    Returns:
        الهاشتاج الجديد
    """
    db_hashtag = models.Hashtag(name=hashtag.name)
    db.add(db_hashtag)
    db.commit()
    db.refresh(db_hashtag)
    return db_hashtag


@router.get("/", response_model=List[schemas.Hashtag])
def get_hashtags(skip: int = 0, limit: int = 100, db: Session = Depends(get_db)):
    """
    الحصول على قائمة الهاشتاجات

    Parameters:
        skip: عدد العناصر المراد تخطيها
        limit: الحد الأقصى للعناصر المسترجعة
        db: جلسة قاعدة البيانات

    Returns:
        قائمة الهاشتاجات
    """
    hashtags = db.query(models.Hashtag).offset(skip).limit(limit).all()
    return hashtags


# Follow/Unfollow Operations
@router.post("/follow/{hashtag_id}")
def follow_hashtag(
    hashtag_id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(oauth2.get_current_user),
):
    """
    متابعة هاشتاج معين

    Parameters:
        hashtag_id: معرف الهاشتاج
        db: جلسة قاعدة البيانات
        current_user: المستخدم الحالي

    Returns:
        رسالة تأكيد نجاح العملية
    """
    hashtag = db.query(models.Hashtag).filter(models.Hashtag.id == hashtag_id).first()
    if not hashtag:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Hashtag not found"
        )

    # التحقق من عدم وجود متابعة مسبقة
    if hashtag in current_user.followed_hashtags:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Already following this hashtag",
        )

    current_user.followed_hashtags.append(hashtag)
    db.commit()
    return {"message": "Hashtag followed successfully"}


@router.post("/unfollow/{hashtag_id}")
def unfollow_hashtag(
    hashtag_id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(oauth2.get_current_user),
):
    """
    إلغاء متابعة هاشتاج

    Parameters:
        hashtag_id: معرف الهاشتاج
        db: جلسة قاعدة البيانات
        current_user: المستخدم الحالي

    Returns:
        رسالة تأكيد نجاح العملية
    """
    hashtag = db.query(models.Hashtag).filter(models.Hashtag.id == hashtag_id).first()
    if not hashtag:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Hashtag not found"
        )

    # التحقق من وجود متابعة
    if hashtag not in current_user.followed_hashtags:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="Not following this hashtag"
        )

    current_user.followed_hashtags.remove(hashtag)
    db.commit()
    return {"message": "Hashtag unfollowed successfully"}


# Analytics and Trending
@router.get("/trending", response_model=List[schemas.Hashtag])
def get_trending_hashtags(db: Session = Depends(get_db), limit: int = 10):
    """
    الحصول على الهاشتاجات الأكثر شعبية

    Parameters:
        db: جلسة قاعدة البيانات
        limit: الحد الأقصى للنتائج

    Returns:
        قائمة الهاشتاجات الأكثر استخداماً
    """
    trending_hashtags = (
        db.query(models.Hashtag)
        .join(models.Post.hashtags)
        .group_by(models.Hashtag.id)
        .order_by(func.count(models.Post.id).desc())
        .limit(limit)
        .all()
    )
    return trending_hashtags


@router.get("/{hashtag_name}/posts", response_model=List[schemas.PostOut])
def get_posts_by_hashtag(
    hashtag_name: str, db: Session = Depends(get_db), skip: int = 0, limit: int = 100
):
    """
    الحصول على المنشورات المرتبطة بهاشتاج معين

    Parameters:
        hashtag_name: اسم الهاشتاج
        db: جلسة قاعدة البيانات
        skip: عدد العناصر المراد تخطيها
        limit: الحد الأقصى للنتائج

    Returns:
        قائمة المنشورات المرتبطة بالهاشتاج
    """
    posts = (
        db.query(models.Post)
        .join(models.Post.hashtags)
        .filter(models.Hashtag.name == hashtag_name)
        .offset(skip)
        .limit(limit)
        .all()
    )

    if not posts:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"No posts found with hashtag: {hashtag_name}",
        )

    return posts


# Statistics and Analytics
@router.get("/{hashtag_id}/statistics", response_model=schemas.HashtagStatistics)
def get_hashtag_statistics(
    hashtag_id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(oauth2.get_current_user),
):
    """
    الحصول على إحصائيات هاشتاج معين

    Parameters:
        hashtag_id: معرف الهاشتاج
        db: جلسة قاعدة البيانات
        current_user: المستخدم الحالي

    Returns:
        إحصائيات الهاشتاج
    """
    hashtag = db.query(models.Hashtag).filter(models.Hashtag.id == hashtag_id).first()
    if not hashtag:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Hashtag not found"
        )

    post_count = (
        db.query(func.count(models.Post.id))
        .join(models.Post.hashtags)
        .filter(models.Hashtag.id == hashtag_id)
        .scalar()
    )

    follower_count = (
        db.query(func.count(models.User.id))
        .join(models.User.followed_hashtags)
        .filter(models.Hashtag.id == hashtag_id)
        .scalar()
    )

    engagement_rate = calculate_engagement_rate(db, hashtag_id)

    return schemas.HashtagStatistics(
        post_count=post_count,
        follower_count=follower_count,
        engagement_rate=engagement_rate,
    )


def calculate_engagement_rate(db: Session, hashtag_id: int) -> float:
    """
    حساب معدل التفاعل مع الهاشتاج

    Parameters:
        db: جلسة قاعدة البيانات
        hashtag_id: معرف الهاشتاج

    Returns:
        معدل التفاعل
    """
    total_interactions = (
        db.query(func.count(models.Vote.id) + func.count(models.Comment.id))
        .join(models.Post.hashtags)
        .outerjoin(models.Vote, models.Vote.post_id == models.Post.id)
        .outerjoin(models.Comment, models.Comment.post_id == models.Post.id)
        .filter(models.Hashtag.id == hashtag_id)
        .scalar()
    )

    post_count = (
        db.query(func.count(models.Post.id))
        .join(models.Post.hashtags)
        .filter(models.Hashtag.id == hashtag_id)
        .scalar()
    )

    if post_count == 0:
        return 0.0

    return total_interactions / post_count
