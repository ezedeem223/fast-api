import pytest
from app import models
from unittest.mock import patch


@pytest.fixture()
def test_vote(test_posts, session, test_user):
    new_vote = models.Vote(post_id=test_posts[3].id, user_id=test_user["id"])
    session.add(new_vote)
    session.commit()
    return new_vote


@patch("app.routers.vote.schedule_email_notification")
def test_vote_on_post(mock_email, authorized_client, test_posts, test_user, session):
    res = authorized_client.post("/vote/", json={"post_id": test_posts[3].id, "dir": 1})
    assert res.status_code == 201
    assert res.json()["message"] == "Successfully added vote"
    vote = (
        session.query(models.Vote)
        .filter(
            models.Vote.post_id == test_posts[3].id,
            models.Vote.user_id == test_user["id"],
        )
        .first()
    )
    assert vote is not None
    mock_email.assert_called_once()


@patch("app.routers.vote.schedule_email_notification")
def test_remove_vote(
    mock_email, authorized_client, test_posts, test_user, test_vote, session
):
    res = authorized_client.post("/vote/", json={"post_id": test_posts[3].id, "dir": 0})
    assert res.status_code == 201
    assert res.json()["message"] == "Successfully deleted vote"
    vote = (
        session.query(models.Vote)
        .filter(
            models.Vote.post_id == test_posts[3].id,
            models.Vote.user_id == test_user["id"],
        )
        .first()
    )
    assert vote is None
    mock_email.assert_called_once()


@patch("app.routers.vote.schedule_email_notification")
def test_vote_twice_post(mock_email, authorized_client, test_posts, test_vote):
    res = authorized_client.post("/vote/", json={"post_id": test_posts[3].id, "dir": 1})
    assert res.status_code == 409
    mock_email.assert_not_called()


@patch("app.routers.vote.schedule_email_notification")
def test_vote_post_non_exist(mock_email, authorized_client, test_posts):
    res = authorized_client.post("/vote/", json={"post_id": 80000, "dir": 1})
    assert res.status_code == 404
    mock_email.assert_not_called()


def test_vote_unauthorized_user(client, test_posts):
    res = client.post("/vote/", json={"post_id": test_posts[0].id, "dir": 1})
    assert res.status_code == 401


@pytest.mark.parametrize("dir_value", [-1, 2])
def test_vote_invalid_direction(dir_value, authorized_client, test_posts):
    res = authorized_client.post(
        "/vote/", json={"post_id": test_posts[0].id, "dir": dir_value}
    )
    assert res.status_code == 422  # Changed from 404 to 422


@patch("app.routers.vote.schedule_email_notification")
def test_vote_own_post(mock_email, authorized_client, test_posts, test_user):
    res = authorized_client.post("/vote/", json={"post_id": test_posts[0].id, "dir": 1})
    assert res.status_code == 201
    mock_email.assert_called_once()


@patch("app.routers.vote.schedule_email_notification")
def test_vote_other_user_post(mock_email, authorized_client, test_posts, test_user):
    res = authorized_client.post("/vote/", json={"post_id": test_posts[3].id, "dir": 1})
    assert res.status_code == 201
    mock_email.assert_called_once()


@pytest.mark.parametrize("dir_value", [0, 1])
@patch("app.routers.vote.schedule_email_notification")
def test_vote_direction(
    mock_email, dir_value, authorized_client, test_posts, session, test_user
):
    res = authorized_client.post(
        "/vote/", json={"post_id": test_posts[0].id, "dir": dir_value}
    )
    assert res.status_code == 201
    vote = (
        session.query(models.Vote)
        .filter(
            models.Vote.post_id == test_posts[0].id,
            models.Vote.user_id == test_user["id"],
        )
        .first()
    )
    if dir_value == 1:
        assert vote is not None
    else:
        assert vote is None
    mock_email.assert_called_once()
