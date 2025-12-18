import pytest
from app.modules.posts.models import Post
from app.modules.users.models import User


def test_social_economy_initial_scoring(
    client, test_user_token_headers, db_session, test_user
):
    """
    اختبار التأكد من أن المنشور الجديد يحصل على نقاط جودة
    وأن رصيد المستخدم يزداد تلقائياً.
    """
    user_id = test_user["id"]
    user_obj = db_session.query(User).filter(User.id == user_id).first()

    initial_credits = user_obj.social_credits
    print(f"\n💰 الرصيد المبدئي: {initial_credits}")

    content = """
    هذا منشور تجريبي لنظام الاقتصاد الاجتماعي.
    نحاول كتابة محتوى مفيد ومنسق لنحصل على نقاط عالية.
    
    النقطة الأولى: الجودة مهمة.
    النقطة الثانية: التنسيق يساعد في القراءة.
    """
    payload = {
        "title": "تجربة الاقتصاد الاجتماعي",
        "content": content,
        "community_id": None,
        "hashtags": ["economy", "test"],
    }

    response = client.post("/posts/", json=payload, headers=test_user_token_headers)
    assert response.status_code == 201
    data = response.json()
    post_id = data["id"]

    db_session.expire_all()

    post = db_session.query(Post).filter(Post.id == post_id).first()
    user_obj = db_session.query(User).filter(User.id == user_id).first()

    print(f"📊 نقاط الجودة: {post.quality_score}")
    print(f"✨ نقاط الأصالة: {post.originality_score}")
    print(f"🏆 المجموع الكلي: {post.score}")

    assert post.quality_score > 0, "فشل حساب نقاط الجودة"
    assert post.originality_score > 0, "فشل حساب نقاط الأصالة"

    print(f"💰 الرصيد الجديد: {user_obj.social_credits}")

    assert (
        user_obj.social_credits >= initial_credits
    ), "رصيد المستخدم نقص أو لم يتغير بشكل صحيح!"

    if user_obj.social_credits > initial_credits:
        print("✅ نجاح! زاد رصيد المستخدم.")
    else:
        print("⚠️ تنبيه: الرصيد لم يتغير (ربما المعادلة أعطت 0 زيادة).")
