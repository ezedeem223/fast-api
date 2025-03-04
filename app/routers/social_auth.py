from fastapi import APIRouter, Depends, Request, HTTPException
from authlib.integrations.starlette_client import OAuth
from starlette.config import Config
from sqlalchemy.orm import Session
from datetime import datetime, timezone, timedelta
import json

from .. import database, models, oauth2, schemas
from ..config import settings
from ..database import get_db

router = APIRouter(tags=["Social Authentication"])

# Initialize config and OAuth with environment variables
config = Config(".env")
oauth = OAuth(config)

# Register Facebook OAuth client
oauth.register(
    name="facebook",
    client_id=settings.facebook_app_id,
    client_secret=settings.facebook_app_secret,
    access_token_url="https://graph.facebook.com/oauth/access_token",
    access_token_params=None,
    authorize_url="https://www.facebook.com/dialog/oauth",
    authorize_params=None,
    api_base_url="https://graph.facebook.com/",
    client_kwargs={"scope": "email"},
)

# Register Twitter OAuth client
oauth.register(
    name="twitter",
    client_id=settings.twitter_api_key,
    client_secret=settings.twitter_api_secret,
    access_token_url="https://api.twitter.com/oauth/access_token",
    access_token_params=None,
    authorize_url="https://api.twitter.com/oauth/authenticate",
    authorize_params=None,
    api_base_url="https://api.twitter.com/1.1/",
    client_kwargs={"scope": "email"},
)

# Register Reddit OAuth client
oauth.register(
    name="reddit",
    client_id=settings.REDDIT_CLIENT_ID,
    client_secret=settings.REDDIT_CLIENT_SECRET,
    authorize_url="https://www.reddit.com/api/v1/authorize",
    access_token_url="https://www.reddit.com/api/v1/access_token",
    api_base_url="https://oauth.reddit.com/api/v1/",
    client_kwargs={"scope": "submit identity"},
)

# Register LinkedIn OAuth client
oauth.register(
    name="linkedin",
    client_id=settings.LINKEDIN_CLIENT_ID,
    client_secret=settings.LINKEDIN_CLIENT_SECRET,
    authorize_url="https://www.linkedin.com/oauth/v2/authorization",
    access_token_url="https://www.linkedin.com/oauth/v2/accessToken",
    api_base_url="https://api.linkedin.com/v2/",
    client_kwargs={"scope": "w_member_social r_liteprofile r_emailaddress"},
)


@router.get("/login/facebook")
async def login_facebook(request: Request):
    """
    Redirect the user to Facebook's OAuth login page.

    Args:
        request (Request): The incoming request.

    Returns:
        A redirect response to Facebook's authorization URL.
    """
    redirect_uri = request.url_for("auth_facebook")
    return await oauth.facebook.authorize_redirect(request, redirect_uri)


@router.get("/auth/facebook")
async def auth_facebook(request: Request, db: Session = Depends(get_db)):
    """
    Handle Facebook OAuth callback.

    - Retrieves the access token and user profile.
    - Creates a new user if one does not exist.
    - Returns an access token for further authentication.

    Args:
        request (Request): The incoming request.
        db (Session): The database session.

    Returns:
        A JSON object containing the access token and token type.
    """
    token = await oauth.facebook.authorize_access_token(request)
    resp = await oauth.facebook.get("me?fields=id,email", token=token)
    profile = resp.json()

    user = db.query(models.User).filter(models.User.email == profile["email"]).first()
    if not user:
        user = models.User(email=profile["email"], facebook_id=profile["id"])
        db.add(user)
        db.commit()
        db.refresh(user)

    access_token = oauth2.create_access_token(data={"user_id": user.id})
    return {"access_token": access_token, "token_type": "bearer"}


@router.get("/login/twitter")
async def login_twitter(request: Request):
    """
    Redirect the user to Twitter's OAuth login page.

    Args:
        request (Request): The incoming request.

    Returns:
        A redirect response to Twitter's authorization URL.
    """
    redirect_uri = request.url_for("auth_twitter")
    return await oauth.twitter.authorize_redirect(request, redirect_uri)


@router.get("/auth/twitter")
async def auth_twitter(request: Request, db: Session = Depends(get_db)):
    """
    Handle Twitter OAuth callback.

    - Retrieves the access token and verifies user credentials.
    - Creates a new user if one does not exist.
    - Returns an access token for further authentication.

    Args:
        request (Request): The incoming request.
        db (Session): The database session.

    Returns:
        A JSON object containing the access token and token type.
    """
    token = await oauth.twitter.authorize_access_token(request)
    resp = await oauth.twitter.get("account/verify_credentials.json", token=token)
    profile = resp.json()

    user = (
        db.query(models.User)
        .filter(models.User.twitter_id == profile["id_str"])
        .first()
    )
    if not user:
        user = models.User(
            twitter_id=profile["id_str"], username=profile["screen_name"]
        )
        db.add(user)
        db.commit()
        db.refresh(user)

    access_token = oauth2.create_access_token(data={"user_id": user.id})
    return {"access_token": access_token, "token_type": "bearer"}


@router.get("/connect/{platform}")
async def connect_social_account(
    platform: schemas.SocialMediaType,
    request: Request,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(oauth2.get_current_user),
):
    """
    Connect a social media account (Reddit or LinkedIn) to the current user.

    Args:
        platform (SocialMediaType): The platform to connect (REDDIT or LINKEDIN).
        request (Request): The incoming request.
        db (Session): The database session.
        current_user (User): The authenticated user.

    Returns:
        A redirect response to the respective platform's OAuth authorization URL.
    """
    if platform == schemas.SocialMediaType.REDDIT:
        return await oauth.reddit.authorize_redirect(
            request, f"{settings.BASE_URL}/social/callback/reddit"
        )
    elif platform == schemas.SocialMediaType.LINKEDIN:
        return await oauth.linkedin.authorize_redirect(
            request, f"{settings.BASE_URL}/social/callback/linkedin"
        )
    else:
        raise HTTPException(
            status_code=400, detail="Unsupported platform for connection"
        )


@router.get("/callback/{platform}")
async def social_callback(
    platform: schemas.SocialMediaType,
    request: Request,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(oauth2.get_current_user),
):
    """
    Handle OAuth callback for social platforms (Reddit or LinkedIn).

    - Retrieves access token and user profile.
    - Saves the social account information to the database.

    Args:
        platform (SocialMediaType): The platform (REDDIT or LINKEDIN).
        request (Request): The incoming request.
        db (Session): The database session.
        current_user (User): The authenticated user.

    Returns:
        A JSON object with a success message.
    """
    if platform == schemas.SocialMediaType.REDDIT:
        token = await oauth.reddit.authorize_access_token(request)
        resp = await oauth.reddit.get("me")
        profile = resp.json()
        account = models.SocialMediaAccount(
            user_id=current_user.id,
            platform=platform,
            access_token=token["access_token"],
            refresh_token=token.get("refresh_token"),
            token_expires_at=datetime.now(timezone.utc)
            + timedelta(seconds=token["expires_in"]),
            account_username=profile["name"],
        )
    elif platform == schemas.SocialMediaType.LINKEDIN:
        token = await oauth.linkedin.authorize_access_token(request)
        resp = await oauth.linkedin.get("me")
        profile = resp.json()
        account = models.SocialMediaAccount(
            user_id=current_user.id,
            platform=platform,
            access_token=token["access_token"],
            refresh_token=token.get("refresh_token"),
            token_expires_at=datetime.now(timezone.utc)
            + timedelta(seconds=token["expires_in"]),
            account_username=f"{profile['localizedFirstName']} {profile['localizedLastName']}",
        )
    else:
        raise HTTPException(status_code=400, detail="Unsupported platform callback")

    db.add(account)
    db.commit()
    db.refresh(account)
    return {"message": f"{platform} account connected successfully"}


@router.delete("/disconnect/{platform}")
async def disconnect_social_account(
    platform: schemas.SocialMediaType,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(oauth2.get_current_user),
):
    """
    Disconnect a social media account from the current user.

    Args:
        platform (SocialMediaType): The platform to disconnect.
        db (Session): The database session.
        current_user (User): The authenticated user.

    Returns:
        A JSON message confirming disconnection.

    Raises:
        HTTPException: If the account is not found.
    """
    account = (
        db.query(models.SocialMediaAccount)
        .filter(
            models.SocialMediaAccount.user_id == current_user.id,
            models.SocialMediaAccount.platform == platform,
            models.SocialMediaAccount.is_active == True,
        )
        .first()
    )
    if not account:
        raise HTTPException(status_code=404, detail="Account not found")

    account.is_active = False
    db.commit()
    return {"message": f"{platform} account disconnected successfully"}
