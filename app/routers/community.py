# تحسين الاستيرادات - إضافة المكتبات اللازمة للوظائف الجديدة
from fastapi import (
    APIRouter,
    Depends,
    HTTPException,
    status,
    Query,
    Request,
    Body,
    Response,
    BackgroundTasks,
)
from sqlalchemy.orm import Session, joinedload
from sqlalchemy import func, or_, desc, asc
from typing import List, Union, Optional
from .. import models, schemas, oauth2
from ..database import get_db
from ..utils import (
    log_user_event,
    create_notification,
    get_translated_content,
    check_content_against_rules,
    check_for_profanity,
    validate_urls,
    analyze_sentiment,
    is_valid_image_url,
    is_valid_video_url,
    detect_language,
    update_post_score,
)
from ..config import settings
import logging
from datetime import date, timedelta, datetime, timezone
import emoji
from fastapi.responses import HTMLResponse, StreamingResponse
import csv
from io import StringIO

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/communities", tags=["Communities"])

# ==================== الثوابت العامة ====================

MAX_PINNED_POSTS = 5
MAX_RULES = 20
ACTIVITY_THRESHOLD_VIP = 1000
INACTIVE_DAYS_THRESHOLD = 30

# ==================== المساعدة والأدوات المساعدة ====================


def check_community_permissions(
    user: models.User,
    community: models.Community,
    required_role: models.CommunityRole,
) -> bool:
    """التحقق من صلاحيات المستخدم في المجتمع"""
    if not community:
        raise HTTPException(status_code=404, detail="المجتمع غير موجود")

    member = next((m for m in community.members if m.user_id == user.id), None)
    if not member:
        raise HTTPException(
            status_code=403, detail="يجب أن تكون عضواً في المجتمع للقيام بهذا الإجراء"
        )

    if member.role not in [
        required_role,
        models.CommunityRole.ADMIN,
        models.CommunityRole.OWNER,
    ]:
        raise HTTPException(
            status_code=403, detail="ليس لديك الصلاحيات الكافية للقيام بهذا الإجراء"
        )

    return True


def update_community_statistics(db: Session, community_id: int):
    """تحديث إحصائيات المجتمع"""
    today = date.today()

    stats = (
        db.query(models.CommunityStatistics)
        .filter(
            models.CommunityStatistics.community_id == community_id,
            models.CommunityStatistics.date == today,
        )
        .first()
    )

    if not stats:
        stats = models.CommunityStatistics(community_id=community_id, date=today)
        db.add(stats)

    # تحديث الإحصائيات الأساسية
    stats.member_count = (
        db.query(models.CommunityMember)
        .filter(models.CommunityMember.community_id == community_id)
        .count()
    )

    # إحصائيات المنشورات والتعليقات
    stats.post_count = (
        db.query(models.Post)
        .filter(
            models.Post.community_id == community_id,
            func.date(models.Post.created_at) == today,
        )
        .count()
    )

    stats.comment_count = (
        db.query(models.Comment)
        .join(models.Post)
        .filter(
            models.Post.community_id == community_id,
            func.date(models.Comment.created_at) == today,
        )
        .count()
    )

    # المستخدمون النشطون
    stats.active_users = (
        db.query(models.CommunityMember)
        .filter(
            models.CommunityMember.community_id == community_id,
            models.CommunityMember.last_active_at >= today - timedelta(days=30),
        )
        .count()
    )

    # التفاعلات والتقييمات
    stats.total_reactions = (
        db.query(func.count(models.Vote.id))
        .join(models.Post)
        .filter(
            models.Post.community_id == community_id,
            func.date(models.Vote.created_at) == today,
        )
        .scalar()
        or 0
    )

    # معدلات النشاط
    if stats.active_users > 0:
        stats.average_posts_per_user = round(stats.post_count / stats.active_users, 2)
        stats.engagement_rate = round(
            (stats.comment_count + stats.total_reactions) / stats.member_count * 100, 2
        )
    else:
        stats.average_posts_per_user = 0
        stats.engagement_rate = 0

    db.commit()
    return stats


# ==================== إنشاء وإدارة المجتمع ====================


@router.post(
    "/",
    status_code=status.HTTP_201_CREATED,
    response_model=schemas.CommunityOut,
    summary="إنشاء مجتمع جديد",
    description="إنشاء مجتمع جديد مع إمكانية تحديد الفئة والوسوم",
)
async def create_community(
    community: schemas.CommunityCreate,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(oauth2.get_current_user),
):
    """إنشاء مجتمع جديد مع التحقق من الصلاحيات وإعداد الإعدادات الأساسية"""
    # التحقق من حالة المستخدم
    if not current_user.is_verified:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="يجب أن يكون حسابك موثقاً لإنشاء مجتمع",
        )

    # التحقق من عدد المجتمعات التي يمتلكها المستخدم
    owned_communities = (
        db.query(models.Community)
        .filter(models.Community.owner_id == current_user.id)
        .count()
    )
    if owned_communities >= settings.MAX_OWNED_COMMUNITIES:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"لا يمكنك إنشاء أكثر من {settings.MAX_OWNED_COMMUNITIES} مجتمع",
        )

    # إنشاء المجتمع
    new_community = models.Community(
        owner_id=current_user.id, **community.dict(exclude={"tags", "rules"})
    )

    # إضافة المؤسس كعضو
    member = models.CommunityMember(
        user_id=current_user.id,
        role=models.CommunityRole.OWNER,
        joined_at=datetime.now(timezone.utc),
    )
    new_community.members.append(member)

    # إضافة الفئة إذا تم تحديدها
    if community.category_id:
        category = (
            db.query(models.Category)
            .filter(models.Category.id == community.category_id)
            .first()
        )
        if not category:
            raise HTTPException(status_code=404, detail="الفئة المحددة غير موجودة")
        new_community.category = category

    # إضافة الوسوم
    if community.tags:
        tags = db.query(models.Tag).filter(models.Tag.id.in_(community.tags)).all()
        new_community.tags.extend(tags)

    # إضافة القواعد الأولية
    if community.rules:
        for rule in community.rules:
            new_rule = models.CommunityRule(
                content=rule.content,
                description=rule.description,
                priority=rule.priority,
            )
            new_community.rules.append(new_rule)

    # حفظ البيانات
    db.add(new_community)
    db.commit()
    db.refresh(new_community)

    # تسجيل الحدث
    log_user_event(
        db, current_user.id, "create_community", {"community_id": new_community.id}
    )

    # إنشاء الإشعار
    create_notification(
        db,
        current_user.id,
        f"تم إنشاء مجتمع جديد: {new_community.name}",
        f"/community/{new_community.id}",
        "new_community",
        new_community.id,
    )

    return schemas.CommunityOut.from_orm(new_community)


# ==================== الاستعلام والبحث ====================


@router.get(
    "/",
    response_model=List[schemas.CommunityOut],
    summary="الحصول على قائمة المجتمعات",
    description="البحث في المجتمعات مع إمكانية التصفية والترتيب",
)
async def get_communities(
    db: Session = Depends(get_db),
    current_user: models.User = Depends(oauth2.get_current_user),
    skip: int = Query(0, ge=0, description="عدد العناصر المراد تخطيها"),
    limit: int = Query(100, ge=1, le=100, description="عدد العناصر المراد عرضها"),
    search: str = Query("", description="نص البحث"),
    category_id: Optional[int] = Query(None, description="معرف الفئة"),
    sort_by: str = Query(
        "created_at",
        description="معيار الترتيب",
        enum=["created_at", "members_count", "activity"],
    ),
    sort_order: str = Query("desc", description="اتجاه الترتيب", enum=["asc", "desc"]),
):
    """الحصول على قائمة المجتمعات مع خيارات البحث والتصفية"""
    query = db.query(models.Community)

    # تطبيق معايير البحث
    if search:
        query = query.filter(
            or_(
                models.Community.name.ilike(f"%{search}%"),
                models.Community.description.ilike(f"%{search}%"),
            )
        )

    # تصفية حسب الفئة
    if category_id:
        query = query.filter(models.Community.category_id == category_id)

    # تطبيق الترتيب
    if sort_by == "created_at":
        query = query.order_by(
            desc(models.Community.created_at)
            if sort_order == "desc"
            else asc(models.Community.created_at)
        )
    elif sort_by == "members_count":
        query = query.order_by(
            desc(models.Community.members_count)
            if sort_order == "desc"
            else asc(models.Community.members_count)
        )
    elif sort_by == "activity":
        query = query.order_by(
            desc(models.Community.last_activity_at)
            if sort_order == "desc"
            else asc(models.Community.last_activity_at)
        )

    # تنفيذ الاستعلام
    communities = query.offset(skip).limit(limit).all()

    # ترجمة المحتوى
    for community in communities:
        community.name = await get_translated_content(
            community.name, current_user, community.language
        )
        community.description = await get_translated_content(
            community.description, current_user, community.language
        )

    return [schemas.CommunityOut.from_orm(community) for community in communities]


@router.get(
    "/{id}",
    response_model=schemas.CommunityOut,
    summary="الحصول على معلومات مجتمع محدد",
)
async def get_community(
    id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(oauth2.get_current_user),
):
    """الحصول على معلومات مجتمع محدد مع البيانات المرتبطة"""
    community = (
        db.query(models.Community)
        .options(
            joinedload(models.Community.members),
            joinedload(models.Community.rules),
            joinedload(models.Community.tags),
            joinedload(models.Community.category),
        )
        .filter(models.Community.id == id)
        .first()
    )

    if not community:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="المجتمع غير موجود"
        )

    # ترجمة المحتوى
    community.name = await get_translated_content(
        community.name, current_user, community.language
    )
    community.description = await get_translated_content(
        community.description, current_user, community.language
    )

    return schemas.CommunityOut.from_orm(community)


# ==================== تحديث وإدارة المجتمع ====================


@router.put(
    "/{id}",
    response_model=schemas.CommunityOut,
    summary="تحديث معلومات المجتمع",
)
async def update_community(
    id: int,
    updated_community: schemas.CommunityUpdate,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(oauth2.get_current_user),
):
    """تحديث معلومات المجتمع مع التحقق من الصلاحيات"""
    community = db.query(models.Community).filter(models.Community.id == id).first()

    if not community:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="المجتمع غير موجود"
        )

    # التحقق من الصلاحيات
    check_community_permissions(current_user, community, models.CommunityRole.OWNER)

    # تحديث البيانات الأساسية
    update_data = updated_community.dict(exclude_unset=True)

    # معالجة الفئة
    if "category_id" in update_data:
        category = (
            db.query(models.Category)
            .filter(models.Category.id == update_data["category_id"])
            .first()
        )
        if not category:
            raise HTTPException(status_code=404, detail="الفئة المحددة غير موجودة")
        community.category = category
        del update_data["category_id"]

    # معالجة الوسوم
    if "tags" in update_data:
        community.tags.clear()
        tags = db.query(models.Tag).filter(models.Tag.id.in_(update_data["tags"])).all()
        community.tags.extend(tags)
        del update_data["tags"]

    # معالجة القواعد
    if "rules" in update_data:
        community.rules.clear()
        for rule_data in update_data["rules"]:
            rule = models.CommunityRule(**rule_data.dict())
            community.rules.append(rule)
        del update_data["rules"]

    # تحديث باقي البيانات
    for key, value in update_data.items():
        setattr(community, key, value)

    community.updated_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(community)

    # إنشاء إشعار
    create_notification(
        db,
        current_user.id,
        f"تم تحديث معلومات مجتمع {community.name}",
        f"/community/{community.id}",
        "update_community",
        community.id,
    )

    return schemas.CommunityOut.from_orm(community)


# ==================== إدارة العضوية ====================


@router.post(
    "/{id}/join",
    status_code=status.HTTP_200_OK,
    summary="الانضمام إلى مجتمع",
)
async def join_community(
    id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(oauth2.get_current_user),
):
    """الانضمام إلى مجتمع مع معالجة القيود والصلاحيات"""
    community = db.query(models.Community).filter(models.Community.id == id).first()

    if not community:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="المجتمع غير موجود"
        )

    # التحقق من عضوية المستخدم
    if any(member.user_id == current_user.id for member in community.members):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="أنت عضو بالفعل في هذا المجتمع",
        )

    # التحقق من القيود
    if community.is_private:
        # التحقق من وجود دعوة
        invitation = (
            db.query(models.CommunityInvitation)
            .filter(
                models.CommunityInvitation.community_id == id,
                models.CommunityInvitation.invitee_id == current_user.id,
                models.CommunityInvitation.status == "pending",
            )
            .first()
        )

        if not invitation:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="هذا المجتمع خاص ويتطلب دعوة للانضمام",
            )

    # إضافة العضو
    new_member = models.CommunityMember(
        community_id=id,
        user_id=current_user.id,
        role=models.CommunityRole.MEMBER,
        joined_at=datetime.now(timezone.utc),
    )

    db.add(new_member)
    community.members_count += 1

    # تحديث حالة الدعوة إذا وجدت
    if community.is_private and invitation:
        invitation.status = "accepted"
        invitation.accepted_at = datetime.now(timezone.utc)

    db.commit()

    # إنشاء إشعار
    create_notification(
        db,
        community.owner_id,
        f"انضم {current_user.username} إلى مجتمع {community.name}",
        f"/community/{id}",
        "new_member",
        current_user.id,
    )

    return {"message": "تم الانضمام إلى المجتمع بنجاح"}


# ==================== إدارة المحتوى ====================


@router.post(
    "/{community_id}/post",
    status_code=status.HTTP_201_CREATED,
    response_model=schemas.PostOut,
    summary="إنشاء منشور جديد في المجتمع",
)
async def create_community_post(
    community_id: int,
    post: schemas.PostCreate,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(oauth2.get_current_user),
):
    """إنشاء منشور جديد في المجتمع مع التحقق من المحتوى والصلاحيات"""

    community = (
        db.query(models.Community).filter(models.Community.id == community_id).first()
    )

    if not community:
        raise HTTPException(status_code=404, detail="المجتمع غير موجود")

    # التحقق من العضوية
    member = next((m for m in community.members if m.user_id == current_user.id), None)

    if not member:
        raise HTTPException(
            status_code=403, detail="يجب أن تكون عضواً في المجتمع لإنشاء منشور"
        )

    # التحقق من المحتوى
    if not post.content.strip():
        raise HTTPException(status_code=400, detail="لا يمكن إنشاء منشور فارغ")

    # فحص المحتوى
    if check_for_profanity(post.content):
        raise HTTPException(status_code=400, detail="المحتوى يحتوي على كلمات غير لائقة")

    # التحقق من القواعد
    if community.rules:
        if not check_content_against_rules(
            post.content, [rule.content for rule in community.rules]
        ):
            raise HTTPException(status_code=400, detail="المحتوى يخالف قواعد المجتمع")

    # إنشاء المنشور
    new_post = models.Post(
        owner_id=current_user.id,
        community_id=community_id,
        content=post.content,
        language=detect_language(post.content),
        has_media=bool(post.media_urls),
        media_urls=post.media_urls,
    )

    db.add(new_post)
    db.commit()
    db.refresh(new_post)

    # تحديث إحصائيات المجتمع
    community.posts_count += 1
    community.last_activity_at = datetime.now(timezone.utc)
    member.posts_count += 1
    member.last_active_at = datetime.now(timezone.utc)

    # التحقق من ترقية العضو
    if (
        member.posts_count >= ACTIVITY_THRESHOLD_VIP
        and member.role == models.CommunityRole.MEMBER
    ):
        member.role = models.CommunityRole.VIP
        create_notification(
            db,
            current_user.id,
            f"تمت ترقيتك إلى عضو VIP في مجتمع {community.name}",
            f"/community/{community_id}",
            "role_upgrade",
            None,
        )

    db.commit()

    # إشعار لمشرفي المجتمع
    for admin in community.members:
        if admin.role in [models.CommunityRole.ADMIN, models.CommunityRole.OWNER]:
            create_notification(
                db,
                admin.user_id,
                f"منشور جديد من {current_user.username} في مجتمع {community.name}",
                f"/post/{new_post.id}",
                "new_post",
                new_post.id,
            )

    return schemas.PostOut.from_orm(new_post)


# ==================== إدارة القواعد ====================


@router.post(
    "/{community_id}/rules",
    response_model=schemas.CommunityRuleOut,
    summary="إضافة قاعدة جديدة للمجتمع",
)
async def add_community_rule(
    community_id: int,
    rule: schemas.CommunityRuleCreate,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(oauth2.get_current_user),
):
    """إضافة قاعدة جديدة للمجتمع مع التحقق من الصلاحيات"""
    community = (
        db.query(models.Community).filter(models.Community.id == community_id).first()
    )

    # التحقق من الصلاحيات
    check_community_permissions(current_user, community, models.CommunityRole.ADMIN)

    # التحقق من عدد القواعد
    existing_rules_count = (
        db.query(models.CommunityRule)
        .filter(models.CommunityRule.community_id == community_id)
        .count()
    )

    if existing_rules_count >= MAX_RULES:
        raise HTTPException(
            status_code=400, detail=f"لا يمكن إضافة أكثر من {MAX_RULES} قاعدة للمجتمع"
        )

    # إنشاء القاعدة
    new_rule = models.CommunityRule(
        community_id=community_id,
        content=rule.content,
        description=rule.description,
        priority=rule.priority,
        created_by=current_user.id,
        created_at=datetime.now(timezone.utc),
    )

    db.add(new_rule)
    db.commit()
    db.refresh(new_rule)

    # إشعار الأعضاء
    for member in community.members:
        create_notification(
            db,
            member.user_id,
            f"تمت إضافة قاعدة جديدة في مجتمع {community.name}",
            f"/community/{community_id}/rules",
            "new_rule",
            new_rule.id,
        )

    return schemas.CommunityRuleOut.from_orm(new_rule)


# ==================== الإحصائيات والتحليلات ====================


@router.get(
    "/{community_id}/analytics",
    response_model=schemas.CommunityAnalytics,
    summary="تحليلات شاملة للمجتمع",
)
async def get_community_analytics(
    community_id: int,
    start_date: date,
    end_date: date,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(oauth2.get_current_user),
):
    """الحصول على تحليلات تفصيلية للمجتمع"""
    community = (
        db.query(models.Community).filter(models.Community.id == community_id).first()
    )

    check_community_permissions(current_user, community, models.CommunityRole.MODERATOR)

    # جمع البيانات الأساسية
    total_members = (
        db.query(models.CommunityMember)
        .filter(models.CommunityMember.community_id == community_id)
        .count()
    )

    # تحليل النشاط
    activity_data = (
        db.query(
            func.date(models.Post.created_at).label("date"),
            func.count(models.Post.id).label("posts"),
            func.count(models.Comment.id).label("comments"),
            func.count(distinct(models.Post.owner_id)).label("active_users"),
        )
        .outerjoin(models.Comment)
        .filter(
            models.Post.community_id == community_id,
            models.Post.created_at.between(start_date, end_date),
        )
        .group_by(func.date(models.Post.created_at))
        .all()
    )

    # تحليل التفاعل
    engagement_data = (
        db.query(
            func.avg(models.Post.likes_count).label("avg_likes"),
            func.avg(models.Post.comments_count).label("avg_comments"),
            func.sum(models.Post.shares_count).label("total_shares"),
        )
        .filter(
            models.Post.community_id == community_id,
            models.Post.created_at.between(start_date, end_date),
        )
        .first()
    )

    # تحليل المحتوى
    content_analysis = (
        db.query(
            models.Post.content_type,
            func.count(models.Post.id).label("count"),
            func.avg(models.Post.likes_count).label("avg_engagement"),
        )
        .filter(
            models.Post.community_id == community_id,
            models.Post.created_at.between(start_date, end_date),
        )
        .group_by(models.Post.content_type)
        .all()
    )

    # معدل النمو
    growth_data = []
    current_date = start_date
    while current_date <= end_date:
        members_count = (
            db.query(models.CommunityMember)
            .filter(
                models.CommunityMember.community_id == community_id,
                models.CommunityMember.joined_at <= current_date,
            )
            .count()
        )
        growth_data.append({"date": current_date, "members": members_count})
        current_date += timedelta(days=1)

    return {
        "overview": {
            "total_members": total_members,
            "active_members": len(set(d.active_users for d in activity_data)),
            "total_posts": sum(d.posts for d in activity_data),
            "total_comments": sum(d.comments for d in activity_data),
        },
        "activity": [
            {
                "date": d.date,
                "posts": d.posts,
                "comments": d.comments,
                "active_users": d.active_users,
            }
            for d in activity_data
        ],
        "engagement": {
            "avg_likes_per_post": round(engagement_data.avg_likes or 0, 2),
            "avg_comments_per_post": round(engagement_data.avg_comments or 0, 2),
            "total_shares": engagement_data.total_shares or 0,
        },
        "content_analysis": [
            {
                "type": c.content_type,
                "count": c.count,
                "avg_engagement": round(c.avg_engagement or 0, 2),
            }
            for c in content_analysis
        ],
        "growth": growth_data,
    }


# ==================== إدارة الأدوار والصلاحيات ====================


@router.put(
    "/{community_id}/members/{user_id}/role",
    response_model=schemas.CommunityMemberOut,
    summary="تحديث دور عضو في المجتمع",
)
async def update_member_role(
    community_id: int,
    user_id: int,
    role_update: schemas.CommunityMemberRoleUpdate,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(oauth2.get_current_user),
):
    """تحديث دور عضو في المجتمع مع التحقق من الصلاحيات"""
    community = (
        db.query(models.Community).filter(models.Community.id == community_id).first()
    )

    check_community_permissions(current_user, community, models.CommunityRole.ADMIN)

    member = (
        db.query(models.CommunityMember)
        .filter(
            models.CommunityMember.community_id == community_id,
            models.CommunityMember.user_id == user_id,
        )
        .first()
    )

    if not member:
        raise HTTPException(status_code=404, detail="العضو غير موجود في المجتمع")

    # التحقق من صلاحية تعيين الدور
    if member.role == models.CommunityRole.OWNER:
        raise HTTPException(status_code=403, detail="لا يمكن تغيير دور مالك المجتمع")

    if role_update.role == models.CommunityRole.OWNER:
        raise HTTPException(status_code=400, detail="لا يمكن تعيين عضو كمالك للمجتمع")

    # حفظ الدور القديم للإشعارات
    old_role = member.role

    # تحديث الدور
    member.role = role_update.role
    member.role_updated_at = datetime.now(timezone.utc)
    member.role_updated_by = current_user.id

    db.commit()
    db.refresh(member)

    # إنشاء إشعار
    create_notification(
        db,
        user_id,
        f"تم تغيير دورك في مجتمع {community.name} من {old_role} إلى {role_update.role}",
        f"/community/{community_id}",
        "role_update",
        None,
    )

    return schemas.CommunityMemberOut.from_orm(member)


# ==================== الدعوات وطلبات الانضمام ====================


@router.post(
    "/{community_id}/invitations",
    status_code=status.HTTP_201_CREATED,
    response_model=schemas.CommunityInvitationOut,
    summary="دعوة أعضاء جدد للمجتمع",
)
async def invite_members(
    community_id: int,
    invitations: List[schemas.CommunityInvitationCreate],
    db: Session = Depends(get_db),
    current_user: models.User = Depends(oauth2.get_current_user),
):
    """دعوة أعضاء جدد للمجتمع مع التحقق من الصلاحيات والقيود"""
    community = (
        db.query(models.Community).filter(models.Community.id == community_id).first()
    )

    check_community_permissions(current_user, community, models.CommunityRole.MEMBER)

    # التحقق من عدد الدعوات المتاحة
    active_invitations = (
        db.query(models.CommunityInvitation)
        .filter(
            models.CommunityInvitation.community_id == community_id,
            models.CommunityInvitation.inviter_id == current_user.id,
            models.CommunityInvitation.status == "pending",
        )
        .count()
    )

    if active_invitations + len(invitations) > settings.MAX_PENDING_INVITATIONS:
        raise HTTPException(
            status_code=400,
            detail=f"لا يمكنك إرسال أكثر من {settings.MAX_PENDING_INVITATIONS} دعوة معلقة",
        )

    created_invitations = []
    for invitation in invitations:
        # التحقق من وجود المستخدم المدعو
        invitee = (
            db.query(models.User)
            .filter(models.User.id == invitation.invitee_id)
            .first()
        )

        if not invitee:
            continue

        # التحقق من عدم وجود دعوة سابقة
        existing_invitation = (
            db.query(models.CommunityInvitation)
            .filter(
                models.CommunityInvitation.community_id == community_id,
                models.CommunityInvitation.invitee_id == invitation.invitee_id,
                models.CommunityInvitation.status == "pending",
            )
            .first()
        )

        if existing_invitation:
            continue

        # التحقق من عدم العضوية
        is_member = (
            db.query(models.CommunityMember)
            .filter(
                models.CommunityMember.community_id == community_id,
                models.CommunityMember.user_id == invitation.invitee_id,
            )
            .first()
        )

        if is_member:
            continue

        # إنشاء الدعوة
        new_invitation = models.CommunityInvitation(
            community_id=community_id,
            inviter_id=current_user.id,
            invitee_id=invitation.invitee_id,
            message=invitation.message,
            expires_at=datetime.now(timezone.utc)
            + timedelta(days=settings.INVITATION_EXPIRY_DAYS),
        )

        db.add(new_invitation)
        created_invitations.append(new_invitation)

        # إنشاء إشعار
        create_notification(
            db,
            invitation.invitee_id,
            f"لديك دعوة للانضمام إلى مجتمع {community.name} من {current_user.username}",
            f"/invitations/{new_invitation.id}",
            "community_invitation",
            new_invitation.id,
        )

    db.commit()

    for invitation in created_invitations:
        db.refresh(invitation)

    return [schemas.CommunityInvitationOut.from_orm(inv) for inv in created_invitations]


# ==================== تصدير البيانات ====================


@router.get(
    "/{community_id}/export",
    response_class=StreamingResponse,
    summary="تصدير بيانات المجتمع",
)
async def export_community_data(
    community_id: int,
    data_type: str = Query(..., enum=["members", "posts", "analytics"]),
    date_from: Optional[date] = None,
    date_to: Optional[date] = None,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(oauth2.get_current_user),
):
    """تصدير بيانات المجتمع بتنسيقات مختلفة"""
    community = (
        db.query(models.Community).filter(models.Community.id == community_id).first()
    )

    check_community_permissions(current_user, community, models.CommunityRole.ADMIN)

    output = StringIO()
    writer = csv.writer(output)

    if data_type == "members":
        # تصدير بيانات الأعضاء
        writer.writerow(
            [
                "معرف العضو",
                "اسم المستخدم",
                "الدور",
                "تاريخ الانضمام",
                "عدد المنشورات",
                "درجة النشاط",
                "آخر نشاط",
            ]
        )

        members = (
            db.query(models.CommunityMember)
            .filter(models.CommunityMember.community_id == community_id)
            .all()
        )

        for member in members:
            writer.writerow(
                [
                    member.user_id,
                    member.user.username,
                    member.role,
                    member.joined_at.strftime("%Y-%m-%d"),
                    member.posts_count,
                    member.activity_score,
                    (
                        member.last_active_at.strftime("%Y-%m-%d %H:%M")
                        if member.last_active_at
                        else "غير متوفر"
                    ),
                ]
            )

    elif data_type == "posts":
        # تصدير بيانات المنشورات
        writer.writerow(
            [
                "معرف المنشور",
                "الكاتب",
                "تاريخ النشر",
                "عدد الإعجابات",
                "عدد التعليقات",
                "نوع المحتوى",
                "الحالة",
            ]
        )

        query = db.query(models.Post).filter(models.Post.community_id == community_id)
        if date_from:
            query = query.filter(models.Post.created_at >= date_from)
        if date_to:
            query = query.filter(models.Post.created_at <= date_to)

        posts = query.all()

        for post in posts:
            writer.writerow(
                [
                    post.id,
                    post.owner.username,
                    post.created_at.strftime("%Y-%m-%d %H:%M"),
                    post.likes_count,
                    post.comments_count,
                    post.content_type,
                    post.status,
                ]
            )

    elif data_type == "analytics":
        # تصدير البيانات التحليلية
        writer.writerow(
            [
                "التاريخ",
                "عدد الأعضاء",
                "المنشورات الجديدة",
                "التعليقات",
                "الأعضاء النشطون",
                "التفاعلات",
                "معدل المشاركة",
            ]
        )

        stats = get_community_statistics(
            db,
            community_id,
            date_from or (datetime.now() - timedelta(days=30)).date(),
            date_to or datetime.now().date(),
        )

        for stat in stats:
            writer.writerow(
                [
                    stat.date.strftime("%Y-%m-%d"),
                    stat.member_count,
                    stat.post_count,
                    stat.comment_count,
                    stat.active_users,
                    stat.total_reactions,
                    f"{stat.engagement_rate:.2f}%",
                ]
            )

    output.seek(0)

    headers = {
        "Content-Disposition": f"attachment; filename=community_{community_id}_{data_type}_{datetime.now().strftime('%Y%m%d')}.csv"
    }

    return StreamingResponse(
        iter([output.getvalue()]), media_type="text/csv", headers=headers
    )


# ==================== معالجة الإشعارات ====================


class CommunityNotificationHandler:
    """معالج إشعارات المجتمع"""

    def __init__(self, db: Session, background_tasks: BackgroundTasks):
        self.db = db
        self.background_tasks = background_tasks
        self.notification_service = NotificationService(db, background_tasks)

    async def handle_new_member(self, community: models.Community, member: models.User):
        """معالجة إشعارات العضو الجديد"""
        # إشعار لمشرفي المجتمع
        admins = [
            m
            for m in community.members
            if m.role in [models.CommunityRole.ADMIN, models.CommunityRole.OWNER]
        ]
        for admin in admins:
            await self.notification_service.create_notification(
                user_id=admin.user_id,
                content=f"انضم {member.username} إلى مجتمع {community.name}",
                notification_type="new_member",
                priority=models.NotificationPriority.LOW,
                category=models.NotificationCategory.COMMUNITY,
                link=f"/community/{community.id}/members",
                metadata={
                    "community_id": community.id,
                    "member_id": member.id,
                },
            )

        # إشعار للعضو الجديد
        await self.notification_service.create_notification(
            user_id=member.id,
            content=f"مرحباً بك في مجتمع {community.name}!",
            notification_type="welcome",
            priority=models.NotificationPriority.HIGH,
            category=models.NotificationCategory.COMMUNITY,
            link=f"/community/{community.id}",
            metadata={
                "community_id": community.id,
                "rules_count": len(community.rules),
            },
        )

    async def handle_content_violation(
        self,
        community: models.Community,
        content: Union[models.Post, models.Comment],
        violation_type: str,
        reporter: models.User,
    ):
        """معالجة إشعارات انتهاك المحتوى"""
        # إشعار للمشرفين
        admins = [
            m
            for m in community.members
            if m.role in [models.CommunityRole.ADMIN, models.CommunityRole.MODERATOR]
        ]

        content_type = "منشور" if isinstance(content, models.Post) else "تعليق"

        for admin in admins:
            await self.notification_service.create_notification(
                user_id=admin.user_id,
                content=f"تم الإبلاغ عن {content_type} في مجتمع {community.name} - نوع الانتهاك: {violation_type}",
                notification_type="content_violation",
                priority=models.NotificationPriority.HIGH,
                category=models.NotificationCategory.MODERATION,
                link=f"/moderation/content/{content.id}",
                metadata={
                    "community_id": community.id,
                    "content_id": content.id,
                    "content_type": content_type,
                    "violation_type": violation_type,
                    "reporter_id": reporter.id,
                },
            )

    async def handle_role_change(
        self,
        community: models.Community,
        member: models.CommunityMember,
        old_role: str,
        changed_by: models.User,
    ):
        """معالجة إشعارات تغيير الأدوار"""
        # إشعار للعضو
        await self.notification_service.create_notification(
            user_id=member.user_id,
            content=f"تم تغيير دورك في مجتمع {community.name} من {old_role} إلى {member.role}",
            notification_type="role_change",
            priority=models.NotificationPriority.HIGH,
            category=models.NotificationCategory.COMMUNITY,
            link=f"/community/{community.id}",
            metadata={
                "community_id": community.id,
                "old_role": old_role,
                "new_role": member.role,
                "changed_by": changed_by.id,
            },
        )

    async def handle_community_achievement(
        self, community: models.Community, achievement_type: str, achievement_data: dict
    ):
        """معالجة إشعارات إنجازات المجتمع"""
        # إشعار لجميع الأعضاء
        for member in community.members:
            await self.notification_service.create_notification(
                user_id=member.user_id,
                content=self._get_achievement_message(
                    achievement_type, achievement_data, community.name
                ),
                notification_type="community_achievement",
                priority=models.NotificationPriority.MEDIUM,
                category=models.NotificationCategory.ACHIEVEMENT,
                link=f"/community/{community.id}/achievements",
                metadata={
                    "community_id": community.id,
                    "achievement_type": achievement_type,
                    **achievement_data,
                },
            )

    def _get_achievement_message(
        self, achievement_type: str, data: dict, community_name: str
    ) -> str:
        """الحصول على رسالة الإنجاز المناسبة"""
        messages = {
            "members_milestone": f"وصل مجتمع {community_name} إلى {data['count']} عضو! 🎉",
            "posts_milestone": f"تم نشر {data['count']} منشور في مجتمع {community_name}! 🎉",
            "engagement_milestone": f"وصل معدل التفاعل في مجتمع {community_name} إلى {data['rate']}%! 🎉",
            "active_streak": f"مجتمع {community_name} نشط لمدة {data['days']} يوم متواصل! 🔥",
        }
        return messages.get(achievement_type, f"إنجاز جديد في مجتمع {community_name}!")


# ==================== المهام الدورية ====================


async def cleanup_expired_invitations(db: Session):
    """تنظيف الدعوات منتهية الصلاحية"""
    expired_invitations = (
        db.query(models.CommunityInvitation)
        .filter(
            models.CommunityInvitation.status == "pending",
            models.CommunityInvitation.expires_at <= datetime.now(timezone.utc),
        )
        .all()
    )

    for invitation in expired_invitations:
        invitation.status = "expired"

        # إشعار المدعو
        create_notification(
            db,
            invitation.invitee_id,
            f"انتهت صلاحية دعوتك للانضمام إلى مجتمع {invitation.community.name}",
            f"/community/{invitation.community_id}",
            "invitation_expired",
            invitation.id,
        )

    db.commit()


async def update_community_rankings(db: Session):
    """تحديث تصنيفات المجتمعات"""
    communities = db.query(models.Community).all()

    for community in communities:
        # حساب درجة النشاط
        activity_score = (
            community.posts_count * 2
            + community.comment_count * 1
            + community.members_count * 3
            + community.total_reactions
        )

        # حساب معدل النمو
        growth_rate = await calculate_community_growth_rate(db, community.id)

        # تحديث التصنيف
        community.activity_score = activity_score
        community.growth_rate = growth_rate
        community.ranking = await calculate_community_ranking(
            activity_score, growth_rate, community.age_in_days
        )

    db.commit()


async def calculate_community_ranking(
    activity_score: float, growth_rate: float, age_in_days: int
) -> float:
    """حساب تصنيف المجتمع بناءً على معايير متعددة"""
    age_factor = min(1.0, age_in_days / 365)  # تطبيع عمر المجتمع

    # معادلة التصنيف المركبة
    ranking = (activity_score * 0.4) + (growth_rate * 0.4) + (age_factor * 0.2)

    return round(ranking, 2)


async def calculate_community_growth_rate(db: Session, community_id: int) -> float:
    """حساب معدل نمو المجتمع"""
    # فترة المقارنة - الشهر الحالي مقابل الشهر السابق
    now = datetime.now(timezone.utc)
    current_month_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    previous_month_start = (current_month_start - timedelta(days=1)).replace(day=1)

    # إحصائيات الشهر الحالي
    current_stats = await get_community_monthly_stats(
        db, community_id, current_month_start
    )

    # إحصائيات الشهر السابق
    previous_stats = await get_community_monthly_stats(
        db, community_id, previous_month_start
    )

    # حساب معدل النمو
    if previous_stats["members"] == 0:
        return 100 if current_stats["members"] > 0 else 0

    growth_rates = {
        "members": (
            (current_stats["members"] - previous_stats["members"])
            / previous_stats["members"]
        )
        * 100,
        "posts": (
            (current_stats["posts"] - previous_stats["posts"]) / previous_stats["posts"]
        )
        * 100,
        "engagement": (
            (current_stats["engagement"] - previous_stats["engagement"])
            / previous_stats["engagement"]
        )
        * 100,
    }

    # معدل النمو المركب
    weighted_growth = (
        (growth_rates["members"] * 0.4)
        + (growth_rates["posts"] * 0.3)
        + (growth_rates["engagement"] * 0.3)
    )

    return round(weighted_growth, 2)
