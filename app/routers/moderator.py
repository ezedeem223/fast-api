from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from typing import List, Optional
from datetime import timedelta

# Import project modules
from .. import models, schemas, oauth2
from ..database import get_db

router = APIRouter(prefix="/moderator", tags=["Moderator"])

# ─── Authentication ─────────────────────────────────────────────────────────────


async def get_current_moderator(
    current_user: models.User = Depends(oauth2.get_current_user),
) -> models.User:
    """
    التحقق من أن المستخدم الحالي لديه صلاحيات المشرف.

    Parameters:
        current_user (models.User): المستخدم الحالي.

    Returns:
        models.User: المستخدم إذا كانت لديه صلاحيات المشرف.

    Raises:
        HTTPException: في حال عدم توفر صلاحيات المشرف.
    """
    if not current_user.is_moderator:
        raise HTTPException(status_code=403, detail="Not authorized")
    return current_user


# ─── Report Management ─────────────────────────────────────────────────────────


@router.get("/community/{community_id}/reports", response_model=List[schemas.ReportOut])
async def get_community_reports(
    community_id: int,
    db: Session = Depends(get_db),
    current_moderator: models.User = Depends(get_current_moderator),
    status_filter: Optional[str] = None,
):
    """
    استرجاع التقارير الخاصة بمجتمع معين.

    Parameters:
        community_id (int): رقم تعريف المجتمع.
        db (Session): جلسة قاعدة البيانات.
        current_moderator (models.User): المشرف الحالي.
        status_filter (Optional[str]): فلتر الحالة إن وجد.

    Returns:
        List[schemas.ReportOut]: قائمة التقارير.

    Raises:
        HTTPException: في حال عدم توفر صلاحيات للوصول للمجتمع.
    """
    # التحقق من صلاحية المشرف في المجتمع
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

    query = (
        db.query(models.Report)
        .join(models.Post)
        .filter(models.Post.community_id == community_id)
    )
    if status_filter:
        query = query.filter(models.Report.status == status_filter)

    return query.all()


@router.put("/reports/{report_id}", response_model=schemas.ReportOut)
async def update_report(
    report_id: int,
    report_update: schemas.ReportUpdate,
    db: Session = Depends(get_db),
    current_moderator: models.User = Depends(get_current_moderator),
):
    """
    تحديث حالة التقرير والملاحظات الخاصة بحله.

    Parameters:
        report_id (int): رقم تعريف التقرير.
        report_update (schemas.ReportUpdate): بيانات التحديث.
        db (Session): جلسة قاعدة البيانات.
        current_moderator (models.User): المشرف الحالي.

    Returns:
        schemas.ReportOut: التقرير المحدث.

    Raises:
        HTTPException: إذا لم يتم العثور على التقرير أو المنشور المرتبط أو صلاحيات الوصول غير كافية.
    """
    report = db.query(models.Report).filter(models.Report.id == report_id).first()
    if not report:
        raise HTTPException(status_code=404, detail="Report not found")

    # التحقق من وجود المنشور المرتبط
    post = db.query(models.Post).filter(models.Post.id == report.post_id).first()
    if not post:
        raise HTTPException(status_code=404, detail="Associated post not found")

    # التحقق من صلاحية المشرف في المجتمع الخاص بالمنشور
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

    report.status = report_update.status
    report.resolution_notes = report_update.resolution_notes
    report.reviewed_by = current_moderator.id
    report.reviewed_at = db.func.now()  # تحديث توقيت المراجعة

    db.commit()
    db.refresh(report)
    return report


# ─── Community Members Management ─────────────────────────────────────────────


@router.get(
    "/community/{community_id}/members", response_model=List[schemas.CommunityMemberOut]
)
async def get_community_members(
    community_id: int,
    db: Session = Depends(get_db),
    current_moderator: models.User = Depends(get_current_moderator),
):
    """
    استرجاع أعضاء المجتمع لمجتمع معين.

    Parameters:
        community_id (int): رقم تعريف المجتمع.
        db (Session): جلسة قاعدة البيانات.
        current_moderator (models.User): المشرف الحالي.

    Returns:
        List[schemas.CommunityMemberOut]: قائمة أعضاء المجتمع.

    Raises:
        HTTPException: إذا لم يكن المشرف مخولاً للوصول للمجتمع.
    """
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
    role_update: schemas.CommunityMemberUpdate,  # تم استبدال CommunityMemberRoleUpdate بـ CommunityMemberUpdate
    db: Session = Depends(get_db),
    current_moderator: models.User = Depends(get_current_moderator),
):
    """
    تحديث دور عضو في المجتمع.

    Parameters:
        community_id (int): رقم تعريف المجتمع.
        user_id (int): رقم تعريف العضو الذي سيتم تحديث دوره.
        role_update (schemas.CommunityMemberUpdate): بيانات الدور الجديد.
        db (Session): جلسة قاعدة البيانات.
        current_moderator (models.User): المشرف الحالي.

    Returns:
        schemas.CommunityMemberOut: السجل المحدث للعضو.

    Raises:
        HTTPException: في حال عدم توفر الصلاحيات أو عدم العثور على العضو.
    """
    # فقط المسؤول (Admin) يمكنه تغيير الأدوار في المجتمع.
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
    member.updated_at = db.func.now()  # تحديث توقيت التعديل
    member.updated_by = current_moderator.id  # تتبع من قام بالتعديل

    db.commit()
    db.refresh(member)
    return member
