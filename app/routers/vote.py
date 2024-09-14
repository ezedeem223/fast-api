import pytest
from app import models
from unittest.mock import patch


@pytest.fixture()
def test_vote(test_posts, session, test_user):
    new_vote = models.Vote(post_id=test_posts[3].id, user_id=test_user.id)
    session.add(new_vote)
    session.commit()
    return new_vote


@patch("app.notifications.send_email_notification")
def test_vote_on_post(
    mock_send_email, authorized_client, test_posts, test_user, session
):
    res = authorized_client.post("/vote/", json={"post_id": test_posts[3].id, "dir": 1})
    assert res.status_code == 201
    response_json = res.json()
    assert "message" in response_json
    assert response_json["message"] == "Successfully added vote"

    vote_in_db = (
        session.query(models.Vote)
        .filter(
            models.Vote.post_id == test_posts[3].id, models.Vote.user_id == test_user.id
        )
        .first()
    )
    assert vote_in_db is not None

    # Verify that send_email_notification was called with correct arguments
    mock_send_email.assert_called_once()
    args, kwargs = mock_send_email.call_args
    assert len(args[0]) == 1  # 'to' should be a list with one email


@patch("app.notifications.send_email_notification")
def test_remove_vote(
    mock_send_email, authorized_client, test_posts, test_user, test_vote, session
):
    res = authorized_client.post("/vote/", json={"post_id": test_posts[3].id, "dir": 0})
    assert res.status_code == 201
    response_json = res.json()
    assert "message" in response_json
    assert response_json["message"] == "Successfully deleted vote"

    vote_in_db = (
        session.query(models.Vote)
        .filter(
            models.Vote.post_id == test_posts[3].id, models.Vote.user_id == test_user.id
        )
        .first()
    )
    assert vote_in_db is None

    # Verify that send_email_notification was called with correct arguments
    mock_send_email.assert_called_once()
    args, kwargs = mock_send_email.call_args
    assert len(args[0]) == 1  # 'to' should be a list with one email
