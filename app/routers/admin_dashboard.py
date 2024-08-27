from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from .. import models, database, oauth2

router = APIRouter(prefix="/admin", tags=["Admin"])


@router.get("/stats")
def get_statistics(
    db: Session = Depends(database.get_db),
    current_user: int = Depends(oauth2.get_current_user),
):
    if not current_user.is_admin:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="Not authorized"
        )

    # إحصائيات بسيطة كأمثلة
    post_count = db.query(models.Post).count()
    user_count = db.query(models.User).count()
    report_count = db.query(models.Report).count()

    return {
        "total_posts": post_count,
        "total_users": user_count,
        "total_reports": report_count,
    }
