from fastapi import APIRouter, Depends, status
from sqlalchemy.orm import Session

from app import models, schemas, oauth2
from app.core.database import get_db
from app.services.reporting import submit_report

router = APIRouter(prefix="/report", tags=["Reports"])


@router.post("/", status_code=status.HTTP_201_CREATED)
def create_report(
    report: schemas.ReportCreate,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(oauth2.get_current_user),
):
    return submit_report(
        db,
        current_user,
        reason=report.reason,
        post_id=report.post_id,
        comment_id=report.comment_id,
    )
