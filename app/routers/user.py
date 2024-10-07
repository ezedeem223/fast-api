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
from sqlalchemy.orm import Session
from sqlalchemy import func
from .. import models, schemas, utils, oauth2
from ..database import get_db
from ..notifications import send_email_notification
from typing import List, Optional
from pydantic import HttpUrl
import pyotp

router = APIRouter(prefix="/users", tags=["Users"])


@router.post("/", status_code=status.HTTP_201_CREATED, response_model=schemas.UserOut)
async def create_user(
    background_tasks: BackgroundTasks,
    user: schemas.UserCreate,
    db: Session = Depends(get_db),
):
    hashed_password = utils.hash(user.password)
    user.password = hashed_password

    new_user = models.User(**user.model_dump())
    db.add(new_user)
    db.commit()
    db.refresh(new_user)

    await send_email_notification(
        to=new_user.email,
        subject="New User Created",
        body=f"A new user with email {new_user.email} has been created.",
    )

    return new_user


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
