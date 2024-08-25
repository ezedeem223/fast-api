from fastapi import APIRouter, Request, Depends, HTTPException, status
from authlib.integrations.starlette_client import OAuth
from sqlalchemy.orm import Session
from .. import database, models, oauth2
from app.config import settings

router = APIRouter(tags=["OAuth"])

# إعداد OAuth مع Google
oauth = OAuth()
google = oauth.register(
    name="google",
    client_id=settings.google_client_id,
    client_secret=settings.google_client_secret,
    authorize_url="https://accounts.google.com/o/oauth2/auth",
    authorize_params=None,
    access_token_url="https://accounts.google.com/o/oauth2/token",
    access_token_params=None,
    refresh_token_url=None,
    redirect_uri="http://localhost:8000/auth/google/callback",
    client_kwargs={"scope": "openid profile email"},
)


# إضافة مسار OAuth2 مع Google
@router.get("/google")
async def auth_google(request: Request):
    redirect_uri = "http://localhost:8000/oauth/google/callback"
    return await oauth.google.authorize_redirect(request, redirect_uri)


@router.get("/google/callback")
async def auth_google_callback(request: Request):
    token = await oauth.google.authorize_access_token(request)
    user_info = await oauth.google.parse_id_token(request, token)

    user_email = user_info.get("email")
    db = database.get_db().__next__()

    # تحقق مما إذا كان المستخدم موجودًا بالفعل
    user = db.query(models.User).filter(models.User.email == user_email).first()

    if not user:
        # إذا لم يكن المستخدم موجودًا، قم بإنشاء حساب جديد
        new_user = models.User(
            email=user_email, password=""
        )  # كلمة المرور فارغة لأنه سيتم الاعتماد على OAuth2
        db.add(new_user)
        db.commit()
        db.refresh(new_user)
        user = new_user

    # إنشاء التوكن
    access_token = oauth2.create_access_token(data={"user_id": user.id})
    return {"access_token": access_token, "token_type": "bearer"}
