from fastapi import APIRouter, Depends, Request, HTTPException
from authlib.integrations.starlette_client import OAuth
from starlette.config import Config
from sqlalchemy.orm import Session
from .. import database, models, oauth2
from ..config import settings

router = APIRouter(tags=["Social Authentication"])

config = Config(".env")
oauth = OAuth(config)

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


@router.get("/login/facebook")
async def login_facebook(request: Request):
    redirect_uri = request.url_for("auth_facebook")
    return await oauth.facebook.authorize_redirect(request, redirect_uri)


@router.get("/auth/facebook")
async def auth_facebook(request: Request, db: Session = Depends(database.get_db)):
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
    redirect_uri = request.url_for("auth_twitter")
    return await oauth.twitter.authorize_redirect(request, redirect_uri)


@router.get("/auth/twitter")
async def auth_twitter(request: Request, db: Session = Depends(database.get_db)):
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
