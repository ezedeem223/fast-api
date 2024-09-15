# import pytest
# from app import models
# from unittest.mock import patch


# @pytest.fixture()
# def test_vote(test_posts, session, test_user):
#     new_vote = models.Vote(post_id=test_posts[3].id, user_id=test_user.id)
#     session.add(new_vote)
#     session.commit()
#     return new_vote


# @patch("app.notifications.send_email_notification")
# def test_vote_on_post(mock_email, authorized_client, test_posts, test_user, session):
#     res = authorized_client.post("/vote/", json={"post_id": test_posts[3].id, "dir": 1})

#     assert res.status_code == 201

#     response_json = res.json()
#     assert "message" in response_json
#     assert response_json["message"] == "Successfully added vote"

#     vote_in_db = (
#         session.query(models.Vote)
#         .filter(
#             models.Vote.post_id == test_posts[3].id, models.Vote.user_id == test_user.id
#         )
#         .first()
#     )
#     assert vote_in_db is not None

#     mock_email.assert_called_once_with(
#         to=test_posts[3].owner.email,
#         subject="New Vote Notification",
#         body="A new vote has been added to your post.",
#     )


# @patch("app.notifications.send_email_notification")
# def test_remove_vote(
#     mock_email, authorized_client, test_posts, test_user, test_vote, session
# ):
#     res = authorized_client.post("/vote/", json={"post_id": test_posts[3].id, "dir": 0})

#     assert res.status_code == 201

#     response_json = res.json()
#     assert "message" in response_json
#     assert response_json["message"] == "Successfully deleted vote"

#     vote_in_db = (
#         session.query(models.Vote)
#         .filter(
#             models.Vote.post_id == test_posts[3].id, models.Vote.user_id == test_user.id
#         )
#         .first()
#     )
#     assert vote_in_db is None

#     mock_email.assert_called_once_with(
#         to=test_posts[3].owner.email,
#         subject="Vote Removed Notification",
#         body="A vote has been removed from your post.",
#     )


# @patch("app.notifications.send_email_notification")
# def test_vote_twice_post(mock_email, authorized_client, test_posts, test_vote):
#     res = authorized_client.post("/vote/", json={"post_id": test_posts[3].id, "dir": 1})
#     assert res.status_code == 409
#     mock_email.assert_not_called()


# @patch("app.notifications.send_email_notification")
# def test_delete_vote(mock_email, authorized_client, test_posts, test_vote):
#     res = authorized_client.post("/vote/", json={"post_id": test_posts[3].id, "dir": 0})
#     assert res.status_code == 201
#     mock_email.assert_called_once()


# @patch("app.notifications.send_email_notification")
# def test_delete_vote_non_exist(mock_email, authorized_client, test_posts):
#     res = authorized_client.post("/vote/", json={"post_id": test_posts[3].id, "dir": 0})
#     assert res.status_code == 404
#     mock_email.assert_not_called()


# @patch("app.notifications.send_email_notification")
# def test_vote_post_non_exist(mock_email, authorized_client, test_posts):
#     res = authorized_client.post("/vote/", json={"post_id": 80000, "dir": 1})
#     assert res.status_code == 404
#     mock_email.assert_not_called()


# @patch("app.notifications.send_email_notification")
# def test_vote_unauthorized_user(mock_email, client, test_posts):
#     res = client.post("/vote/", json={"post_id": test_posts[3].id, "dir": 1})
#     assert res.status_code == 401
#     mock_email.assert_not_called()
