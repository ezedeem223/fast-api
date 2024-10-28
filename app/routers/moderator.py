from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from .. import models, schemas, oauth2
from ..database import get_db
from typing import List, Optional

router = APIRouter(prefix="/moderator", tags=["Moderator"])

# ─── المصادقة ─────────────────────────────────────────────────────────────────────


async def get_current_moderator(
    current_user: models.User = Depends(oauth2.get_current_user),
) -> models.User:
    """التحقق من صلاحيات المشرف

    Parameters:
        current_user: المستخدم الحالي

    Returns:
        models.User: المستخدم إذا كان مشرفاً

    Raises:
        HTTPException: إذا لم يكن المستخدم مشرفاً
    """
    if not current_user.is_moderator:
        raise HTTPException(status_code=403, detail="Not authorized")
    return current_user


# ─── إدارة التقارير ─────────────────────────────────────────────────────────────


@router.get("/community/{community_id}/reports", response_model=List[schemas.ReportOut])
async def get_community_reports(
    community_id: int,
    db: Session = Depends(get_db),
    current_moderator: models.User = Depends(get_current_moderator),
    status: Optional[str] = None,
):
    """الحصول على تقارير المجتمع

    Parameters:
        community_id: معرف المجتمع
        db: جلسة قاعدة البيانات
        current_moderator: المشرف الحالي
        status: حالة التقارير للتصفية (اختياري)

    Returns:
        List[schemas.ReportOut]: قائمة التقارير
    """
    # التحقق من صلاحيات المشرف في المجتمع
    moderator_role = (
        db.query(models.CommunityMember)
        .filter(
            models.CommunityMember.user_id == current_moderator.id,
            models.CommunityMember.community_id == community_id,
            models.CommunityMember.role.in_(
                [models.CommunityRole.MODERATOR, models.CommunityRole.ADMIN]
            ),
        )
        .first()
    )

    if not moderator_role:
        raise HTTPException(status_code=403, detail="Not authorized for this community")

    # بناء استعلام التقارير
    query = (
        db.query(models.Report)
        .join(models.Post)
        .filter(models.Post.community_id == community_id)
    )

    # تطبيق فلتر الحالة إذا تم تحديده
    if status:
        query = query.filter(models.Report.status == status)

    return query.all()


@router.put("/reports/{report_id}", response_model=schemas.ReportOut)
async def update_report(
    report_id: int,
    report_update: schemas.ReportUpdate,
    db: Session = Depends(get_db),
    current_moderator: models.User = Depends(get_current_moderator),
):
    """تحديث حالة التقرير

    Parameters:
        report_id: معرف التقرير
        report_update: بيانات التحديث
        db: جلسة قاعدة البيانات
        current_moderator: المشرف الحالي

    Returns:
        schemas.ReportOut: التقرير المحدث
    """
    report = db.query(models.Report).filter(models.Report.id == report_id).first()
    if not report:
        raise HTTPException(status_code=404, detail="Report not found")

    # التحقق من وجود المنشور المرتبط
    post = db.query(models.Post).filter(models.Post.id == report.post_id).first()
    if not post:
        raise HTTPException(status_code=404, detail="Associated post not found")

    # التحقق من صلاحيات المشرف
    moderator_role = (
        db.query(models.CommunityMember)
        .filter(
            models.CommunityMember.user_id == current_moderator.id,
            models.CommunityMember.community_id == post.community_id,
            models.CommunityMember.role.in_(
                [models.CommunityRole.MODERATOR, models.CommunityRole.ADMIN]
            ),
        )
        .first()
    )

    if not moderator_role:
        raise HTTPException(status_code=403, detail="Not authorized for this community")

    # تحديث التقرير
    report.status = report_update.status
    report.resolution_notes = report_update.resolution_notes
    report.reviewed_by = current_moderator.id
    report.reviewed_at = db.func.now()

    db.commit()
    db.refresh(report)
    return report


# ─── إدارة الأعضاء ─────────────────────────────────────────────────────────────


@router.get(
    "/community/{community_id}/members", response_model=List[schemas.CommunityMemberOut]
)
async def get_community_members(
    community_id: int,
    db: Session = Depends(get_db),
    current_moderator: models.User = Depends(get_current_moderator),
):
    """الحصول على قائمة أعضاء المجتمع

    Parameters:
        community_id: معرف المجتمع
        db: جلسة قاعدة البيانات
        current_moderator: المشرف الحالي

    Returns:
        List[schemas.CommunityMemberOut]: قائمة الأعضاء
    """
    # التحقق من صلاحيات المشرف
    moderator_role = (
        db.query(models.CommunityMember)
        .filter(
            models.CommunityMember.user_id == current_moderator.id,
            models.CommunityMember.community_id == community_id,
            models.CommunityMember.role.in_(
                [models.CommunityRole.MODERATOR, models.CommunityRole.ADMIN]
            ),
        )
        .first()
    )

    if not moderator_role:
        raise HTTPException(status_code=403, detail="Not authorized for this community")

    return (
        db.query(models.CommunityMember)
        .filter(models.CommunityMember.community_id == community_id)
        .all()
    )


@router.put(
    "/community/{community_id}/member/{user_id}/role",
    response_model=schemas.CommunityMemberOut,
)
async def update_member_role(
    community_id: int,
    user_id: int,
    role_update: schemas.CommunityMemberRoleUpdate,
    db: Session = Depends(get_db),
    current_moderator: models.User = Depends(get_current_moderator),
):
    """تحديث دور عضو في المجتمع

    Parameters:
        community_id: معرف المجتمع
        user_id: معرف العضو
        role_update: معلومات تحديث الدور
        db: جلسة قاعدة البيانات
        current_moderator: المشرف الحالي

    Returns:
        schemas.CommunityMemberOut: العضو المحدث
    """
    # التحقق من أن المشرف هو مسؤول في المجتمع
    moderator_role = (
        db.query(models.CommunityMember)
        .filter(
            models.CommunityMember.user_id == current_moderator.id,
            models.CommunityMember.community_id == community_id,
            models.CommunityMember.role == models.CommunityRole.ADMIN,
        )
        .first()
    )

    if not moderator_role:
        raise HTTPException(
            status_code=403, detail="Not authorized to change roles in this community"
        )

    # تحديث دور العضو
    member = (
        db.query(models.CommunityMember)
        .filter(
            models.CommunityMember.community_id == community_id,
            models.CommunityMember.user_id == user_id,
        )
        .first()
    )

    if not member:
        raise HTTPException(
            status_code=404, detail="Member not found in this community"
        )

    member.role = role_update.role
    member.updated_at = db.func.now()
    member.updated_by = current_moderator.id

    db.commit()
    db.refresh(member)
    return member
