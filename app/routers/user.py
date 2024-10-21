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
from sqlalchemy import func, or_, desc, asc
from .. import models, schemas, utils, oauth2, crypto
from ..database import get_db
from ..notifications import send_email_notification
from typing import List, Optional
from pydantic import HttpUrl
import pyotp
from datetime import timedelta
from ..cache import cache
from ..utils import log_user_event
from ..i18n import ALL_LANGUAGES


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


@router.get("/users/{user_id}/followers", response_model=schemas.FollowersListOut)
@cache(expire=300)
async def get_user_followers(
    user_id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(oauth2.get_current_user),
    sort_by: schemas.SortOption = Query(schemas.SortOption.DATE),
    order: str = Query("desc", enum=["asc", "desc"]),
    skip: int = 0,
    limit: int = 100,
):
    user = db.query(models.User).filter(models.User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    if user.followers_visibility == "private" and user.id != current_user.id:
        raise HTTPException(status_code=403, detail="Followers list is private")

    if user.followers_visibility == "custom":
        if (
            user.id != current_user.id
            and current_user.id
            not in user.followers_custom_visibility.get("allowed_users", [])
        ):
            raise HTTPException(
                status_code=403,
                detail="You don't have permission to view this followers list",
            )

    query = (
        db.query(models.Follow)
        .join(models.User, models.User.id == models.Follow.follower_id)
        .filter(models.Follow.followed_id == user_id)
    )

    if sort_by == schemas.SortOption.DATE:
        order_column = models.Follow.created_at
    elif sort_by == schemas.SortOption.USERNAME:
        order_column = models.User.username
    elif sort_by == schemas.SortOption.POST_COUNT:
        order_column = models.User.post_count
    elif sort_by == schemas.SortOption.INTERACTION_COUNT:
        order_column = models.User.interaction_count

    if order == "desc":
        query = query.order_by(desc(order_column))
    else:
        query = query.order_by(asc(order_column))

    total_count = query.count()
    followers = query.offset(skip).limit(limit).all()

    return {
        "followers": [
            schemas.FollowerOut(
                id=follow.follower.id,
                username=follow.follower.username,
                follow_date=follow.created_at,
                post_count=follow.follower.post_count,
                interaction_count=follow.follower.interaction_count,
            )
            for follow in followers
        ],
        "total_count": total_count,
    }


@router.put(
    "/users/me/followers-settings", response_model=schemas.UserFollowersSettings
)
async def update_followers_settings(
    settings: schemas.UserFollowersSettings,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(oauth2.get_current_user),
):
    current_user.followers_visibility = settings.followers_visibility
    current_user.followers_custom_visibility = settings.followers_custom_visibility
    current_user.followers_sort_preference = settings.followers_sort_preference
    db.commit()
    return settings


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
    log_user_event(db, current_user.id, "update_profile")

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


@router.get("/suggested-follows", response_model=List[schemas.UserOut])
def get_suggested_follows(
    db: Session = Depends(get_db),
    current_user: models.User = Depends(oauth2.get_current_user),
    limit: int = 10,
):
    """
    Get suggested users to follow based on shared interests and connections.
    """
    if not current_user.interests:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="User has no interests set"
        )

    # Get users with similar interests
    similar_interests = (
        db.query(models.User.id)
        .filter(models.User.id != current_user.id)
        .filter(models.User.interests.overlap(current_user.interests))
        .subquery()
    )

    # Get users who are followed by users that the current user follows
    followed_by_current_user = (
        db.query(models.Follow.followed_id)
        .filter(models.Follow.follower_id == current_user.id)
        .subquery()
    )
    followers_of_followed = (
        db.query(models.Follow.follower_id)
        .filter(models.Follow.followed_id.in_(followed_by_current_user))
        .subquery()
    )

    suggested_users = (
        db.query(models.User)
        .outerjoin(similar_interests, models.User.id == similar_interests.c.id)
        .outerjoin(
            followers_of_followed, models.User.id == followers_of_followed.c.follower_id
        )
        .filter(models.User.id != current_user.id)
        .filter(~models.User.id.in_(followed_by_current_user))
        .group_by(models.User.id)
        .order_by(
            func.count(similar_interests.c.id).desc(),
            func.count(followers_of_followed.c.follower_id).desc(),
        )
        .limit(limit)
        .all()
    )

    return suggested_users


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


@router.put("/block-settings", response_model=schemas.UserOut)
async def update_block_settings(
    settings: schemas.BlockSettings,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(oauth2.get_current_user),
):
    current_user.default_block_type = settings.default_block_type
    db.commit()
    db.refresh(current_user)
    return current_user


@router.put("/settings/reposts", response_model=schemas.UserOut)
def update_repost_settings(
    settings: schemas.UserUpdate,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(oauth2.get_current_user),
):
    if settings.allow_reposts is not None:
        current_user.allow_reposts = settings.allow_reposts
        db.commit()
        db.refresh(current_user)

    return current_user


@router.get("/notifications", response_model=List[schemas.NotificationOut])
def get_user_notifications(
    db: Session = Depends(get_db),
    current_user: models.User = Depends(oauth2.get_current_user),
    skip: int = 0,
    limit: int = 10,
):
    notifications = (
        db.query(models.Notification)
        .filter(models.Notification.user_id == current_user.id)
        .order_by(desc(models.Notification.created_at))
        .offset(skip)
        .limit(limit)
        .all()
    )

    return notifications


@router.put(
    "/notifications/{notification_id}/read", response_model=schemas.NotificationOut
)
def mark_notification_as_read(
    notification_id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(oauth2.get_current_user),
):
    notification = (
        db.query(models.Notification)
        .filter(
            models.Notification.id == notification_id,
            models.Notification.user_id == current_user.id,
        )
        .first()
    )

    if not notification:
        raise HTTPException(status_code=404, detail="Notification not found")

    notification.is_read = True
    db.commit()
    db.refresh(notification)

    return notification


def log_user_activity(db: Session, user_id: int, activity_type: str, details: dict):
    activity = UserActivity(
        user_id=user_id, activity_type=activity_type, details=details
    )
    db.add(activity)
    db.commit()


@router.post("/users/{user_id}/suspend")
def suspend_user(user_id: int, days: int, db: Session = Depends(get_db)):
    user = db.query(User).filter(User.id == user_id).first()
    user.is_suspended = True
    user.suspension_end_date = datetime.utcnow() + timedelta(days=days)
    db.commit()
    return {"message": "User suspended successfully"}


@router.post("/users/{user_id}/unsuspend")
def unsuspend_user(user_id: int, db: Session = Depends(get_db)):
    user = db.query(User).filter(User.id == user_id).first()
    user.is_suspended = False
    user.suspension_end_date = None
    db.commit()
    return {"message": "User unsuspended successfully"}


@router.put("/users/me/language")
def update_user_language(
    language: UserLanguageUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    if language.preferred_language not in ALL_LANGUAGES:
        raise HTTPException(status_code=400, detail="Invalid language code")

    current_user.preferred_language = language.preferred_language
    current_user.auto_translate = language.auto_translate
    db.commit()
    return {"message": "Language preferences updated successfully"}


@router.get("/languages")
def get_language_options():
    return [{"code": code, "name": name} for code, name in ALL_LANGUAGES.items()]
