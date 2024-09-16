from fastapi import (
    FastAPI,
    Response,
    status,
    HTTPException,
    Depends,
    APIRouter,
    BackgroundTasks,
    UploadFile,
)
from sqlalchemy.orm import Session
from .. import models, schemas, utils, oauth2
from ..database import get_db
from ..notifications import send_email_notification

router = APIRouter(prefix="/users", tags=["Users"])


@router.post("/", status_code=status.HTTP_201_CREATED, response_model=schemas.UserOut)
async def create_user(
    background_tasks: BackgroundTasks,
    user: schemas.UserCreate,
    db: Session = Depends(get_db),
):
    hashed_password = utils.hash(user.password)
    user.password = hashed_password

    new_user = models.User(**user.dict())
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
):
    user = db.query(models.User).filter(models.User.id == id).first()
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"User with id: {id} does not exist",
        )
    return user


@router.post("/verify")
async def verify_user(
    background_tasks: BackgroundTasks,
    file: UploadFile,
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
