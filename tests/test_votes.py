import pytest
from app import models
from unittest.mock import patch


@pytest.fixture()
def test_vote(test_posts, session, test_user):
    # إضافة تصويت جديد إلى قاعدة البيانات
    new_vote = models.Vote(post_id=test_posts[3].id, user_id=test_user.id)
    session.add(new_vote)
    session.commit()
    return new_vote  # أضف الإرجاع لتسهيل الاختبار


@patch("app.notifications.schedule_email_notification")
def test_vote_on_post(mock_email, authorized_client, test_posts, test_user, session):
    # إجراء طلب التصويت
    res = authorized_client.post("/vote/", json={"post_id": test_posts[3].id, "dir": 1})

    # التحقق من أن الاستجابة تحتوي على الحالة الصحيحة
    assert res.status_code == 201

    # التحقق من تفاصيل الاستجابة إذا كانت تحتوي على معلومات
    response_json = res.json()
    assert "message" in response_json
    assert response_json["message"] == "Successfully added vote"

    # التحقق من أن التصويت قد تم تسجيله في قاعدة البيانات
    vote_in_db = (
        session.query(models.Vote)
        .filter(
            models.Vote.post_id == test_posts[3].id, models.Vote.user_id == test_user.id
        )
        .first()
    )
    assert vote_in_db is not None

    # التحقق من أن دالة إرسال البريد الإلكتروني قد تم استدعاؤها
    mock_email.assert_called_once()


# اختبار إضافي للتحقق من حالة إزالة التصويت
@patch("app.notifications.schedule_email_notification")
def test_remove_vote(
    mock_email, authorized_client, test_posts, test_user, test_vote, session
):
    # إجراء طلب إزالة التصويت
    res = authorized_client.post("/vote/", json={"post_id": test_posts[3].id, "dir": 0})

    # التحقق من أن الاستجابة تحتوي على الحالة الصحيحة
    assert res.status_code == 201

    # التحقق من تفاصيل الاستجابة
    response_json = res.json()
    assert "message" in response_json
    assert response_json["message"] == "Successfully deleted vote"

    # التحقق من أن التصويت قد تمت إزالته من قاعدة البيانات
    vote_in_db = (
        session.query(models.Vote)
        .filter(
            models.Vote.post_id == test_posts[3].id, models.Vote.user_id == test_user.id
        )
        .first()
    )
    assert vote_in_db is None

    # التحقق من أن دالة إرسال البريد الإلكتروني قد تم استدعاؤها
    mock_email.assert_called_once()


# def test_vote_twice_post(authorized_client, test_posts, test_vote):
#     res = authorized_client.post("/vote/", json={"post_id": test_posts[3].id, "dir": 1})
#     assert res.status_code == 409


# def test_delete_vote(authorized_client, test_posts, test_vote):
#     res = authorized_client.post("/vote/", json={"post_id": test_posts[3].id, "dir": 0})
#     assert res.status_code == 201


# def test_delete_vote_non_exist(authorized_client, test_posts):
#     res = authorized_client.post("/vote/", json={"post_id": test_posts[3].id, "dir": 0})
#     assert res.status_code == 404


# def test_vote_post_non_exist(authorized_client, test_posts):
#     res = authorized_client.post("/vote/", json={"post_id": 80000, "dir": 1})
#     assert res.status_code == 404


# def test_vote_unauthorized_user(client, test_posts):
#     res = client.post("/vote/", json={"post_id": test_posts[3].id, "dir": 1})
#     assert res.status_code == 401
