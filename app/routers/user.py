from fastapi import (
    FastAPI,
    Response,
    status,
    HTTPException,
    Depends,
    APIRouter,
    BackgroundTasks,
    UploadFile,
    File,
)
from sqlalchemy.orm import Session, joinedload
from sqlalchemy import func, or_
from .. import models, schemas, utils, oauth2, crypto
from ..database import get_db
from ..notifications import send_email_notification
from typing import List, Optional
from pydantic import HttpUrl
import pyotp
from datetime import timedelta

router = APIRouter(prefix="/users", tags=["Users"])


@router.post("/", status_code=status.HTTP_201_CREATED, response_model=schemas.UserOut)
async def create_user(
    background_tasks: BackgroundTasks,
    user: schemas.UserCreate,
    db: Session = Depends(get_db),
):
    # التحقق من وجود المستخدم
    existing_user = (
        db.query(models.User).filter(models.User.email == user.email).first()
    )
    if existing_user:
        raise HTTPException(status_code=400, detail="Email already registered")

    # تشفير كلمة المرور
    hashed_password = utils.hash(user.password)

    # إنشاء مستخدم جديد
    new_user = models.User(
        email=user.email,
        hashed_password=hashed_password,
        public_key=user.public_key,
        **user.model_dump(exclude={"password", "public_key"}),
    )
    db.add(new_user)
    db.commit()
    db.refresh(new_user)

    # إرسال إشعار بالبريد الإلكتروني
    background_tasks.add_task(
        send_email_notification,
        to=new_user.email,
        subject="New User Created",
        body=f"A new user with email {new_user.email} has been created.",
    )

    return new_user


@router.put("/public-key", response_model=schemas.UserOut)
def update_public_key(
    key_update: schemas.UserPublicKeyUpdate,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(oauth2.get_current_user),
):
    current_user.public_key = key_update.public_key
    db.commit()
    db.refresh(current_user)
    return current_user


@router.get("/{id}", response_model=schemas.UserOut)
def get_user(
    id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(oauth2.get_current_user),
):
    user = db.query(models.User).filter(models.User.id == id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    if user.privacy_level == models.PrivacyLevel.PRIVATE and user.id != current_user.id:
        raise HTTPException(status_code=403, detail="This profile is private")

    if user.privacy_level == models.PrivacyLevel.CUSTOM:
        allowed_users = user.custom_privacy.get("allowed_users", [])
        if current_user.id not in allowed_users and user.id != current_user.id:
            raise HTTPException(
                status_code=403, detail="You don't have permission to view this profile"
            )

    return user


@router.post("/verify")
async def verify_user(
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    current_user: models.User = Depends(oauth2.get_current_user),
    db: Session = Depends(get_db),
):
    if file.content_type not in ["image/jpeg", "image/png", "application/pdf"]:
        raise HTTPException(status_code=400, detail="Unsupported file type.")

    file_location = f"static/{file.filename}"
    with open(file_location, "wb+") as file_object:
        file_object.write(file.file.read())

    current_user.verification_document = file_location
    current_user.is_verified = True
    db.commit()

    await send_email_notification(
        to=current_user.email,
        subject="Verification Completed",
        body=f"Your account has been verified successfully.",
    )

    return {"info": "Verification document uploaded and user verified successfully."}


@router.get("/my-content", response_model=schemas.UserContentOut)
async def get_user_content(
    db: Session = Depends(get_db),
    current_user: models.User = Depends(oauth2.get_current_user),
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=100),
):
    if not current_user:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Not authorized to access this content",
        )

    # استعلام المنشورات مع مراعاة الخصوصية
    posts_query = db.query(models.Post).filter(models.Post.owner_id == current_user.id)

    # إذا كانت إعدادات الخصوصية مخصصة، نطبق القيود المخصصة
    if current_user.privacy_level == models.PrivacyLevel.CUSTOM:
        allowed_users = current_user.custom_privacy.get("allowed_users", [])
        posts_query = posts_query.filter(
            or_(
                models.Post.privacy_level == models.PrivacyLevel.PUBLIC,
                models.Post.id.in_(allowed_users),
            )
        )
    elif current_user.privacy_level == models.PrivacyLevel.PRIVATE:
        # إذا كان الملف الشخصي خاص، نعرض جميع المنشورات للمستخدم نفسه
        pass
    else:  # PUBLIC
        # نعرض جميع المنشورات العامة
        posts_query = posts_query.filter(
            models.Post.privacy_level == models.PrivacyLevel.PUBLIC
        )

    posts = (
        posts_query.options(joinedload(models.Post.owner))
        .order_by(models.Post.created_at.desc())
        .offset(skip)
        .limit(limit)
        .all()
    )

    # استعلامات التعليقات والمقالات والفيديوهات القصيرة تبقى كما هي
    comments = (
        db.query(models.Comment)
        .filter(models.Comment.owner_id == current_user.id)
        .options(joinedload(models.Comment.post))
        .order_by(models.Comment.created_at.desc())
        .offset(skip)
        .limit(limit)
        .all()
    )

    articles = (
        db.query(models.Article)
        .filter(models.Article.author_id == current_user.id)
        .options(joinedload(models.Article.author))
        .order_by(models.Article.created_at.desc())
        .offset(skip)
        .limit(limit)
        .all()
    )

    reels = (
        db.query(models.Reel)
        .filter(models.Reel.owner_id == current_user.id)
        .options(joinedload(models.Reel.owner))
        .order_by(models.Reel.created_at.desc())
        .offset(skip)
        .limit(limit)
        .all()
    )

    return schemas.UserContentOut(
        posts=[schemas.PostOut.from_orm(post) for post in posts],
        comments=[schemas.Comment.from_orm(comment) for comment in comments],
        articles=[schemas.ArticleOut.from_orm(article) for article in articles],
        reels=[schemas.ReelOut.from_orm(reel) for reel in reels],
    )


@router.get("/my-content", response_model=schemas.UserContentOut)
async def get_user_content(
    db: Session = Depends(get_db),
    current_user: models.User = Depends(oauth2.get_current_user),
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=100),
):
    # التحقق من أن المستخدم يطلب محتواه الخاص فقط
    if not current_user:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Not authorized to access this content",
        )


@router.put("/profile", response_model=schemas.UserProfileOut)
def update_user_profile(
    profile_update: schemas.UserProfileUpdate,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(oauth2.get_current_user),
):
    for key, value in profile_update.dict(exclude_unset=True).items():
        setattr(current_user, key, value)

    db.commit()
    db.refresh(current_user)
    return get_user_profile(current_user.id, db)


@router.put("/privacy", response_model=schemas.UserOut)
def update_privacy_settings(
    privacy_settings: schemas.UserPrivacyUpdate,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(oauth2.get_current_user),
):
    if (
        privacy_settings.privacy_level == schemas.PrivacyLevel.CUSTOM
        and not privacy_settings.custom_privacy
    ):
        raise HTTPException(
            status_code=400,
            detail="Custom privacy settings required for CUSTOM privacy level",
        )

    current_user.privacy_level = privacy_settings.privacy_level
    if privacy_settings.custom_privacy:
        current_user.custom_privacy = privacy_settings.custom_privacy

    db.commit()
    db.refresh(current_user)
    return current_user


@router.get("/profile/{user_id}", response_model=schemas.UserProfileOut)
def get_user_profile(user_id: int, db: Session = Depends(get_db)):
    user = db.query(models.User).filter(models.User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    post_count = (
        db.query(func.count(models.Post.id))
        .filter(models.Post.owner_id == user_id)
        .scalar()
    )
    follower_count = (
        db.query(func.count(models.Follow.follower_id))
        .filter(models.Follow.followed_id == user_id)
        .scalar()
    )
    following_count = (
        db.query(func.count(models.Follow.followed_id))
        .filter(models.Follow.follower_id == user_id)
        .scalar()
    )
    community_count = (
        db.query(func.count(models.CommunityMember.user_id))
        .filter(models.CommunityMember.user_id == user_id)
        .scalar()
    )
    media_count = (
        db.query(func.count(models.Post.id))
        .filter(
            models.Post.owner_id == user_id,
            models.Post.content.like("%image%") | models.Post.content.like("%video%"),
        )
        .scalar()
    )

    return schemas.UserProfileOut(
        id=user.id,
        email=user.email,
        profile_image=user.profile_image,
        bio=user.bio,
        location=user.location,
        website=user.website,
        joined_at=user.joined_at,
        post_count=post_count,
        follower_count=follower_count,
        following_count=following_count,
        community_count=community_count,
        media_count=media_count,
    )


@router.get("/profile/{user_id}/posts", response_model=List[schemas.PostOut])
def get_user_posts(
    user_id: int, db: Session = Depends(get_db), skip: int = 0, limit: int = 10
):
    posts = (
        db.query(models.Post)
        .filter(models.Post.owner_id == user_id)
        .offset(skip)
        .limit(limit)
        .all()
    )
    return [schemas.PostOut.from_orm(post) for post in posts]


@router.get("/profile/{user_id}/articles", response_model=List[schemas.ArticleOut])
def get_user_articles(
    user_id: int, db: Session = Depends(get_db), skip: int = 0, limit: int = 10
):
    articles = (
        db.query(models.Article)
        .filter(models.Article.author_id == user_id)
        .offset(skip)
        .limit(limit)
        .all()
    )
    return [schemas.ArticleOut.from_orm(article) for article in articles]


@router.get("/profile/{user_id}/media", response_model=List[schemas.PostOut])
def get_user_media(
    user_id: int, db: Session = Depends(get_db), skip: int = 0, limit: int = 10
):
    media = (
        db.query(models.Post)
        .filter(
            models.Post.owner_id == user_id,
            models.Post.content.like("%image%") | models.Post.content.like("%video%"),
        )
        .offset(skip)
        .limit(limit)
        .all()
    )
    return [schemas.PostOut.from_orm(item) for item in media]


@router.get("/profile/{user_id}/likes", response_model=List[schemas.PostOut])
def get_user_likes(
    user_id: int, db: Session = Depends(get_db), skip: int = 0, limit: int = 10
):
    liked_posts = (
        db.query(models.Post)
        .join(models.Vote)
        .filter(models.Vote.user_id == user_id)
        .offset(skip)
        .limit(limit)
        .all()
    )
    return [schemas.PostOut.from_orm(post) for post in liked_posts]


@router.post("/profile/image")
async def upload_profile_image(
    file: UploadFile = File(...),
    current_user: models.User = Depends(oauth2.get_current_user),
    db: Session = Depends(get_db),
):
    if file.content_type not in ["image/jpeg", "image/png"]:
        raise HTTPException(
            status_code=400,
            detail="Unsupported file type. Only JPEG and PNG are allowed.",
        )

    file_location = f"static/profile_images/{current_user.id}_{file.filename}"
    with open(file_location, "wb+") as file_object:
        file_object.write(file.file.read())

    current_user.profile_image = file_location
    db.commit()

    return {"info": "Profile image uploaded successfully."}


@router.post("/change-password")
def change_password(
    password_change: schemas.PasswordChange,
    current_user: models.User = Depends(oauth2.get_current_user),
    db: Session = Depends(get_db),
):
    if not utils.verify(password_change.current_password, current_user.password):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="Incorrect password"
        )

    hashed_password = utils.hash(password_change.new_password)
    current_user.password = hashed_password
    db.commit()
    return {"message": "Password changed successfully"}


@router.post("/enable-2fa", response_model=schemas.Enable2FAResponse)
def enable_2fa(
    current_user: models.User = Depends(oauth2.get_current_user),
    db: Session = Depends(get_db),
):
    if current_user.otp_secret:
        raise HTTPException(status_code=400, detail="2FA is already enabled")

    secret = pyotp.random_base32()
    current_user.otp_secret = secret
    db.commit()

    return {"otp_secret": secret}


@router.post("/verify-2fa")
def verify_2fa(
    otp: str,
    current_user: models.User = Depends(oauth2.get_current_user),
    db: Session = Depends(get_db),
):
    if not current_user.otp_secret:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="2FA is not enabled for this user.",
        )

    totp = pyotp.TOTP(current_user.otp_secret)
    if not totp.verify(otp):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid OTP"
        )

    return {"message": "2FA verified successfully"}


@router.post("/disable-2fa")
def disable_2fa(
    current_user: models.User = Depends(oauth2.get_current_user),
    db: Session = Depends(get_db),
):
    if not current_user.otp_secret:
        raise HTTPException(status_code=400, detail="2FA is not enabled")

    current_user.otp_secret = None
    db.commit()

    return {"message": "2FA disabled successfully"}


@router.post("/logout-all-devices")
def logout_all_devices(
    current_user: models.User = Depends(oauth2.get_current_user),
    current_session: str = Depends(oauth2.get_current_session),
    db: Session = Depends(get_db),
):
    db.query(models.UserSession).filter(
        models.UserSession.user_id == current_user.id,
        models.UserSession.session_id != current_session,
    ).delete()
    db.commit()
    return {"message": "Logged out from all other devices"}


@router.get("/users/similar-interests", response_model=List[schemas.UserOut])
def get_users_with_similar_interests(
    db: Session = Depends(get_db),
    current_user: models.User = Depends(oauth2.get_current_user),
    limit: int = 10,
):
    if not current_user.interests:
        raise HTTPException(status_code=400, detail="User has no interests set")

    similar_users = (
        db.query(models.User)
        .filter(models.User.id != current_user.id)
        .filter(models.User.interests.overlap(current_user.interests))
        .order_by(
            func.array_length(
                func.array_intersect(models.User.interests, current_user.interests), 1
            ).desc()
        )
        .limit(limit)
        .all()
    )
    return similar_users


@router.get("/analytics", response_model=schemas.UserAnalytics)
async def get_user_analytics(
    db: Session = Depends(get_db),
    current_user: models.User = Depends(oauth2.get_current_user),
    days: int = Query(30, ge=1, le=365),
):
    end_date = date.today()
    start_date = end_date - timedelta(days=days)

    daily_stats = (
        db.query(models.UserStatistics)
        .filter(
            models.UserStatistics.user_id == current_user.id,
            models.UserStatistics.date.between(start_date, end_date),
        )
        .all()
    )

    totals = (
        db.query(
            func.sum(models.UserStatistics.post_count).label("total_posts"),
            func.sum(models.UserStatistics.comment_count).label("total_comments"),
            func.sum(models.UserStatistics.like_count).label("total_likes"),
            func.sum(models.UserStatistics.view_count).label("total_views"),
        )
        .filter(models.UserStatistics.user_id == current_user.id)
        .first()
    )

    return schemas.UserAnalytics(
        total_posts=totals.total_posts or 0,
        total_comments=totals.total_comments or 0,
        total_likes=totals.total_likes or 0,
        total_views=totals.total_views or 0,
        daily_statistics=daily_stats,
    )


@router.get("/settings", response_model=schemas.UserSettings)
async def get_user_settings(
    current_user: models.User = Depends(oauth2.get_current_user),
):
    return schemas.UserSettings(
        ui_settings=schemas.UISettings(**current_user.ui_settings),
        notifications_settings=schemas.NotificationsSettings(
            **current_user.notifications_settings
        ),
    )


@router.put("/settings", response_model=schemas.UserSettings)
async def update_user_settings(
    settings: schemas.UserSettingsUpdate,
    current_user: models.User = Depends(oauth2.get_current_user),
    db: Session = Depends(get_db),
):
    if settings.ui_settings:
        current_user.ui_settings.update(settings.ui_settings.dict(exclude_unset=True))
    if settings.notifications_settings:
        current_user.notifications_settings.update(
            settings.notifications_settings.dict(exclude_unset=True)
        )

    db.commit()
    db.refresh(current_user)

    return schemas.UserSettings(
        ui_settings=schemas.UISettings(**current_user.ui_settings),
        notifications_settings=schemas.NotificationsSettings(
            **current_user.notifications_settings
        ),
    )
