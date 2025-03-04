from fastapi import APIRouter, Request, Depends, HTTPException, status
from authlib.integrations.starlette_client import OAuth
from sqlalchemy.orm import Session
from .. import database, models, oauth2
from app.config import settings

router = APIRouter(tags=["OAuth"])

# Initialize OAuth and register Google OAuth settings
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


@router.get("/google")
async def auth_google(request: Request):
    """
    Initiate the Google OAuth login process.

    Parameters:
        request (Request): The incoming HTTP request.

    Returns:
        A redirect response to Google's OAuth authorization endpoint.
    """
    redirect_uri = "http://localhost:8000/auth/google/callback"
    return await oauth.google.authorize_redirect(request, redirect_uri)


@router.get("/google/callback")
async def auth_google_callback(
    request: Request, db: Session = Depends(database.get_db)
):
    """
    Handle the callback from Google OAuth, create a new user if not existing, and generate an access token.

    Parameters:
        request (Request): The incoming HTTP request.
        db (Session): Database session dependency.

    Returns:
        dict: A JSON object containing the access token and token type.

    Raises:
        HTTPException: If an error occurs during authentication.
    """
    try:
        # Retrieve access token from Google
        token = await oauth.google.authorize_access_token(request)
        # Parse the ID token to get user information
        user_info = await oauth.google.parse_id_token(request, token)
        user_email = user_info.get("email")

        if not user_email:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Google did not provide an email address.",
            )

        # Check if the user already exists in the database
        user = db.query(models.User).filter(models.User.email == user_email).first()

        if not user:
            # Create a new user if not found
            new_user = models.User(
                email=user_email,
                password="",  # Password is empty because OAuth is used
                is_verified=True,  # Mark the user as verified via Google
            )
            db.add(new_user)
            db.commit()
            db.refresh(new_user)
            user = new_user

        # Create an access token for the authenticated user
        access_token = oauth2.create_access_token(data={"user_id": user.id})
        return {"access_token": access_token, "token_type": "bearer"}

    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error during Google authentication: {str(e)}",
        )
