from fastapi import (
    APIRouter,
    Depends,
    HTTPException,
    status,
    UploadFile,
    File,
    BackgroundTasks,
    Form,
)
from sqlalchemy.orm import Session
from typing import List
from .. import models, schemas, oauth2, notifications
from ..database import get_db
from fastapi.responses import FileResponse
import clamd
import os

router = APIRouter(prefix="/message", tags=["Messages"])


@router.post("/", status_code=status.HTTP_201_CREATED, response_model=schemas.Message)
def send_message(
    message: schemas.MessageCreate,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(oauth2.get_current_user),
):
    recipient = (
        db.query(models.User).filter(models.User.id == message.recipient_id).first()
    )
    if not recipient:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="User not found",
        )

    block = (
        db.query(models.Block)
        .filter(
            models.Block.blocker_id == message.recipient_id,
            models.Block.blocked_id == current_user.id,
        )
        .first()
    )

    if block:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="You can't send messages to this user",
        )

    new_message = models.Message(
        sender_id=current_user.id,
        receiver_id=message.recipient_id,
        content=message.content,
    )
    db.add(new_message)
    db.commit()
    db.refresh(new_message)

    return new_message


@router.get("/", response_model=List[schemas.Message])
def get_messages(
    db: Session = Depends(get_db),
    current_user: models.User = Depends(oauth2.get_current_user),
    skip: int = 0,
    limit: int = 500,
):
    messages = (
        db.query(models.Message)
        .filter(
            (models.Message.sender_id == current_user.id)
            | (models.Message.receiver_id == current_user.id)
        )
        .order_by(models.Message.timestamp.desc())
        .offset(skip)
        .limit(limit)
        .all()
    )
    return list(map(schemas.Message.from_orm, messages))


@router.get("/inbox", response_model=List[schemas.MessageOut])
def get_inbox(
    db: Session = Depends(get_db),
    current_user: models.User = Depends(oauth2.get_current_user),
    skip: int = 0,
    limit: int = 100,
):
    messages = (
        db.query(models.Message)
        .filter(models.Message.receiver_id == current_user.id)
        .order_by(models.Message.timestamp.desc())
        .offset(skip)
        .limit(limit)
        .all()
    )
    return [
        schemas.MessageOut(message=schemas.Message.from_orm(message), count=1)
        for message in messages
    ]


@router.post("/send_file", status_code=status.HTTP_201_CREATED)
async def send_file(
    file: UploadFile = File(...),
    recipient_id: int = Form(...),
    db: Session = Depends(get_db),
    current_user: models.User = Depends(oauth2.get_current_user),
    background_tasks: BackgroundTasks = BackgroundTasks(),
):
    recipient = db.query(models.User).filter(models.User.id == recipient_id).first()
    if not recipient:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="User not found"
        )

    # Check if file is empty
    await file.seek(0)
    file_content = await file.read()
    await file.seek(0)  # Reset file pointer

    if len(file_content) == 0 or file.filename == "":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="File is empty"
        )

    file_size = len(file_content)

    if file_size > 10 * 1024 * 1024:  # 10MB
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail="File is too large",
        )

    file_location = f"static/messages/{file.filename}"

    os.makedirs(os.path.dirname(file_location), exist_ok=True)

    with open(file_location, "wb") as file_object:
        file_object.write(file_content)

    if not scan_file_for_viruses(file_location):
        os.remove(file_location)
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="File is infected with a virus.",
        )

    new_message = models.Message(
        sender_id=current_user.id, receiver_id=recipient_id, content=file_location
    )
    db.add(new_message)
    db.commit()
    db.refresh(new_message)

    background_tasks.add_task(
        notifications.schedule_email_notification,
        background_tasks=background_tasks,
        to=recipient.email,
        subject="New File Received",
        body=f"You have received a file from {current_user.email}.",
    )

    return {"message": "File sent successfully"}


def scan_file_for_viruses(file_path: str) -> bool:
    cd = clamd.ClamdNetworkSocket()
    result = cd.scan(file_path)
    if result and result[file_path][0] == "FOUND":
        return False
    return True


@router.get("/download/{file_name}")
def download_file(
    file_name: str,
    current_user: models.User = Depends(oauth2.get_current_user),
    db: Session = Depends(get_db),
):
    message = (
        db.query(models.Message)
        .filter(models.Message.content == f"static/messages/{file_name}")
        .first()
    )
    if not message or (
        message.sender_id != current_user.id and message.receiver_id != current_user.id
    ):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="File not found"
        )

    file_path = f"static/messages/{file_name}"
    if not os.path.exists(file_path):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="File not found"
        )
    return FileResponse(path=file_path, filename=file_name)


# asd
