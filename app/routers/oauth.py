from authlib.integrations.starlette_client import OAuth
from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.orm import Session

from .. import models, oauth2
from app.core.config import settings
from app.core.database import get_db

router = APIRouter(tags=["OAuth"])


def _get_callback_url(request: Request, name: str) -> str:
    return str(request.url_for(name))


def _issue_token_for_email(db: Session, email: str | None) -> dict:
    if not email:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Unable to retrieve an email address from the OAuth provider.",
        )
    user = db.query(models.User).filter(models.User.email == email).first()
    if not user:
        user = models.User(email=email, password="", is_verified=True)
        db.add(user)
        db.commit()
        db.refresh(user)
    access_token = oauth2.create_access_token({"user_id": user.id})
    return {"access_token": access_token, "token_type": "bearer"}


oauth = OAuth()

oauth.register(
    name="google",
    client_id=settings.google_client_id,
    client_secret=settings.google_client_secret,
    authorize_url="https://accounts.google.com/o/oauth2/auth",
    access_token_url="https://accounts.google.com/o/oauth2/token",
    client_kwargs={"scope": "openid profile email"},
)

oauth.register(
    name="facebook",
    client_id=settings.facebook_app_id,
    client_secret=settings.facebook_app_secret,
    authorize_url="https://www.facebook.com/v19.0/dialog/oauth",
    access_token_url="https://graph.facebook.com/v19.0/oauth/access_token",
    client_kwargs={"scope": "email"},
)

oauth.register(
    name="twitter",
    client_id=settings.twitter_api_key,
    client_secret=settings.twitter_api_secret,
    request_token_url="https://api.twitter.com/oauth/request_token",
    authorize_url="https://api.twitter.com/oauth/authorize",
    access_token_url="https://api.twitter.com/oauth/access_token",
    api_base_url="https://api.twitter.com/1.1/",
)


@router.get("/google")
async def auth_google(request: Request):
    redirect_uri = _get_callback_url(request, "auth_google_callback")
    return await oauth.google.authorize_redirect(request, redirect_uri)


@router.get("/google/callback")
async def auth_google_callback(
    request: Request,
    db: Session = Depends(get_db),
):
    try:
        token = await oauth.google.authorize_access_token(request)
        user_info = await oauth.google.parse_id_token(request, token)
        return _issue_token_for_email(db, user_info.get("email"))
    except HTTPException:
        raise
    except Exception as exc:  # pragma: no cover - defensive fallback
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Google authentication failed: {exc}",
        ) from exc


@router.get("/facebook")
async def auth_facebook(request: Request):
    redirect_uri = _get_callback_url(request, "auth_facebook_callback")
    return await oauth.facebook.authorize_redirect(request, redirect_uri)


@router.get("/facebook/callback")
async def auth_facebook_callback(
    request: Request,
    db: Session = Depends(get_db),
):
    try:
        token = await oauth.facebook.authorize_access_token(request)
        resp = await oauth.facebook.get(
            "https://graph.facebook.com/me?fields=id,name,email",
            token=token,
        )
        profile = resp.json()
        return _issue_token_for_email(db, profile.get("email"))
    except HTTPException:
        raise
    except Exception as exc:  # pragma: no cover
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Facebook authentication failed: {exc}",
        ) from exc


@router.get("/twitter")
async def auth_twitter(request: Request):
    redirect_uri = _get_callback_url(request, "auth_twitter_callback")
    return await oauth.twitter.authorize_redirect(request, redirect_uri)


@router.get("/twitter/callback")
async def auth_twitter_callback(
    request: Request,
    db: Session = Depends(get_db),
):
    try:
        token = await oauth.twitter.authorize_access_token(request)
        resp = await oauth.twitter.get(
            "account/verify_credentials.json?include_email=true",
            token=token,
        )
        profile = resp.json()
        email = profile.get("email")
        if not email and profile.get("screen_name"):
            email = f"{profile['screen_name']}@twitter.local"
        return _issue_token_for_email(db, email)
    except HTTPException:
        raise
    except Exception as exc:  # pragma: no cover
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Twitter authentication failed: {exc}",
        ) from exc
