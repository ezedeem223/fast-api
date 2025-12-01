import pytest
from app.modules.posts.models import Post, Reaction

# التصحيح: Vote موجود في social وليس posts
from app.modules.social.models import Vote
from app.modules.users.models import User
from app.modules.social.economy_service import SocialEconomyService


def test_score_updates_on_vote(
    client, test_user_token_headers, db_session, test_user, test_post
):
    """
    اختبار: نقاط المنشور يجب أن تزيد عند إضافة تصويت (Like).
    """
    # 1. تحضير المنشور وحساب نقاطه الأولية
    post_id = test_post["id"]

    # نضمن أن المنشور لديه نقاط أولية
    service = SocialEconomyService(db_session)
    service.update_post_score(post_id)
    db_session.commit()

    # جلب النقاط الحالية (يجب تحديث الجلسة لرؤية التغييرات)
    db_session.expire_all()
    post_before = db_session.query(Post).filter(Post.id == post_id).first()
    initial_score = post_before.score
    print(f"\n📊 النقاط قبل اللايك: {initial_score}")

    # 2. القيام بعملية تصويت (Like) عبر الـ API
    # ملاحظة: نستخدم reaction_type لأن الخدمة تتعامل مع Reactions
    vote_payload = {"post_id": post_id, "reaction_type": "like"}

    # نرسل الطلب إلى مسار reactions (تأكد أن هذا المسار موجود في routers/reaction.py)
    response = client.post(
        "/reactions/", json=vote_payload, headers=test_user_token_headers
    )

    # إذا فشل هنا بـ 404، فهذا يعني أن الراوتر غير مسجل بـ prefix='/reactions'
    assert response.status_code in [200, 201], f"فشل التصويت: {response.text}"

    # 3. التحقق من زيادة النقاط
    db_session.expire_all()
    post_after = db_session.query(Post).filter(Post.id == post_id).first()
    new_score = post_after.score
    print(f"📈 النقاط بعد اللايك: {new_score}")

    # يجب أن تزيد النقاط
    assert new_score > initial_score, "فشل النظام! النقاط لم تزد بعد التفاعل."
    print("✅ نجاح! نظام الاقتصاد يعمل ديناميكياً.")


def test_score_updates_on_comment(
    client, test_user_token_headers, db_session, test_user, test_post
):
    """
    اختبار: نقاط المنشور يجب أن تزيد عند إضافة تعليق.
    """
    post_id = test_post["id"]

    # حساب النقاط الحالية
    service = SocialEconomyService(db_session)
    service.update_post_score(post_id)
    db_session.commit()

    db_session.expire_all()
    post_before = db_session.query(Post).filter(Post.id == post_id).first()
    initial_score = post_before.score

    # إضافة تعليق
    comment_payload = {
        "content": "هذا تعليق رائع يزيد من قيمة المنشور!",
        "post_id": post_id,
    }

    response = client.post(
        "/comments/", json=comment_payload, headers=test_user_token_headers
    )
    assert response.status_code == 201

    # التحقق
    db_session.expire_all()
    post_after = db_session.query(Post).filter(Post.id == post_id).first()

    print(f"📈 النقاط بعد التعليق: {post_after.score}")
    assert post_after.score > initial_score, "فشل النظام! النقاط لم تزد بعد التعليق."
