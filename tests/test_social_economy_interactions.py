from app.modules.posts.models import Post
from app.modules.social.economy_service import SocialEconomyService


def test_score_updates_on_vote(
    client, test_user_token_headers, db_session, test_user, test_post
):
    """
    اختبار: نقاط المنشور يجب أن تزيد عند إضافة تصويت (Like).
    """
    post_id = test_post["id"]

    service = SocialEconomyService(db_session)
    service.update_post_score(post_id)
    db_session.commit()

    db_session.expire_all()
    post_before = db_session.query(Post).filter(Post.id == post_id).first()
    initial_score = post_before.score
    print(f"\n📊 النقاط قبل اللايك: {initial_score}")

    vote_payload = {"post_id": post_id, "reaction_type": "like"}

    response = client.post(
        "/reactions/", json=vote_payload, headers=test_user_token_headers
    )

    assert response.status_code in [200, 201], f"فشل التصويت: {response.text}"

    db_session.expire_all()
    post_after = db_session.query(Post).filter(Post.id == post_id).first()
    new_score = post_after.score
    print(f"📈 النقاط بعد اللايك: {new_score}")

    assert new_score > initial_score, "فشل النظام! النقاط لم تزد بعد التفاعل."
    print("✅ نجاح! نظام الاقتصاد يعمل ديناميكياً.")


def test_score_updates_on_comment(
    client, test_user_token_headers, db_session, test_user, test_post
):
    """
    اختبار: نقاط المنشور يجب أن تزيد عند إضافة تعليق.
    """
    post_id = test_post["id"]

    service = SocialEconomyService(db_session)
    service.update_post_score(post_id)
    db_session.commit()

    db_session.expire_all()
    post_before = db_session.query(Post).filter(Post.id == post_id).first()
    initial_score = post_before.score

    comment_payload = {
        "content": "هذا تعليق رائع يزيد من قيمة المنشور!",
        "post_id": post_id,
    }

    response = client.post(
        "/comments/", json=comment_payload, headers=test_user_token_headers
    )
    assert response.status_code == 201

    db_session.expire_all()
    post_after = db_session.query(Post).filter(Post.id == post_id).first()

    print(f"📈 النقاط بعد التعليق: {post_after.score}")
    assert post_after.score > initial_score, "فشل النظام! النقاط لم تزد بعد التعليق."
