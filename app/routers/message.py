from fastapi import (
    APIRouter,
    Depends,
    HTTPException,
    status,
    UploadFile,
    File,
    BackgroundTasks,
)
from sqlalchemy.orm import Session
from typing import List
from .. import models, schemas, oauth2, notifications
from ..database import get_db
from fastapi.responses import FileResponse
import clamd
import os

router = APIRouter(prefix="/messages", tags=["Messages"])


@router.post("/", status_code=status.HTTP_201_CREATED)
def send_message(
    recipient_id: int,
    message: str,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(oauth2.get_current_user),
    background_tasks: BackgroundTasks = BackgroundTasks(),  # تعديل هنا
):
    new_message = models.Message(
        sender_id=current_user.id, receiver_id=recipient_id, content=message
    )
    db.add(new_message)
    db.commit()
    db.refresh(new_message)

    # إرسال إشعار للمستلم
    background_tasks.add_task(
        notifications.send_notification,
        user_id=recipient_id,
        message=f"You have received a new message from {current_user.email}.",
    )

    return new_message


@router.get("/", response_model=List[schemas.Message])
def get_messages(
    db: Session = Depends(get_db),
    current_user: models.User = Depends(oauth2.get_current_user),
):
    messages = (
        db.query(models.Message)
        .filter(
            (models.Message.sender_id == current_user.id)
            | (models.Message.receiver_id == current_user.id)
        )
        .all()
    )
    return messages


@router.get("/inbox", response_model=List[schemas.MessageOut])
def get_inbox(
    db: Session = Depends(get_db),
    current_user: models.User = Depends(oauth2.get_current_user),
):
    messages = (
        db.query(models.Message)
        .filter(models.Message.receiver_id == current_user.id)
        .order_by(models.Message.timestamp.desc())
        .all()
    )
    return messages


@router.post("/send_file")
def send_file(
    recipient_id: int,
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    current_user: models.User = Depends(oauth2.get_current_user),
    background_tasks: BackgroundTasks = BackgroundTasks(),  # تعديل هنا
):
    # إنشاء مسار الملف المؤقت
    file_location = f"static/messages/{file.filename}"

    # تأكد من إنشاء المجلد إذا لم يكن موجودًا
    os.makedirs(os.path.dirname(file_location), exist_ok=True)

    with open(file_location, "wb+") as file_object:
        file_object.write(file.file.read())

    # فحص الملف للتأكد من خلوه من الفيروسات
    if not scan_file_for_viruses(file_location):
        os.remove(file_location)  # إزالة الملف إذا كان مصابًا
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

    # إرسال إشعار للمستلم
    background_tasks.add_task(
        notifications.send_notification,
        user_id=recipient_id,
        message=f"You have received a file from {current_user.email}.",
    )

    return {"message": "File sent successfully"}


def scan_file_for_viruses(file_path: str) -> bool:
    cd = clamd.ClamdNetworkSocket()
    result = cd.scan(file_path)
    if result and result[file_path][0] == "FOUND":
        return False
    return True


@router.get("/download/{file_name}")
def download_file(file_name: str):
    file_path = f"static/messages/{file_name}"
    if not os.path.exists(file_path):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="File not found"
        )
    return FileResponse(path=file_path, filename=file_name)
