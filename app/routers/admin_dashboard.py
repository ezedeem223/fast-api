from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from .. import models, database, oauth2

router = APIRouter(prefix="/admin", tags=["Admin"])


@router.get("/stats")
def get_statistics(
    db: Session = Depends(database.get_db),
    current_user: models.User = Depends(oauth2.get_current_user),
):
    # تحقق من صلاحيات المسؤول
    if not current_user.is_admin:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="Not authorized"
        )

    try:
        # إحصائيات بسيطة كأمثلة
        post_count = db.query(models.Post).count()
        user_count = db.query(models.User).count()
        report_count = db.query(models.Report).count()

        return {
            "total_posts": post_count,
            "total_users": user_count,
            "total_reports": report_count,
        }
    except Exception as e:
        # إدارة الاستثناءات
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An error occurred while fetching statistics.",
        )
