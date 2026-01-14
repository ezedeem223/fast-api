"""Test module for test votes."""
from unittest.mock import patch

import pytest

from app import models


@pytest.fixture()
def test_reaction(test_posts, session, test_user):
    """Pytest fixture for test_reaction."""
    reaction = models.Reaction(
        post_id=test_posts[3].id,
        user_id=test_user["id"],
        reaction_type=models.ReactionType.LIKE.value,
    )
    session.add(reaction)
    session.commit()
    return reaction


def _patch_email():
    """Helper for  patch email."""
    return patch("app.routers.vote.queue_email_notification"), patch(
        "app.routers.vote.schedule_email_notification"
    )


def _get_reaction(session, post_id, user_id):
    """Helper for  get reaction."""
    return (
        session.query(models.Reaction)
        .filter(
            models.Reaction.post_id == post_id,
            models.Reaction.user_id == user_id,
        )
        .first()
    )


def test_vote_on_post(authorized_client, test_posts, test_user, session):
    """Test case for test vote on post."""
    post_id = test_posts[3].id
    with _patch_email()[0] as mock_queue, _patch_email()[1] as mock_schedule:
        res = authorized_client.post(
            "/vote/", json={"post_id": post_id, "reaction_type": "like"}
        )
    assert res.status_code == 201
    assert res.json()["message"] == "Successfully added like reaction"
    reaction = _get_reaction(session, post_id, test_user["id"])
    assert reaction is not None
    assert reaction.reaction_type == models.ReactionType.LIKE
    mock_queue.assert_called_once()
    mock_schedule.assert_called_once()


def test_remove_vote(authorized_client, test_posts, test_user, session, test_reaction):
    """Test case for test remove vote."""
    post_id = test_posts[3].id
    with _patch_email()[0] as mock_queue, _patch_email()[1] as mock_schedule:
        res = authorized_client.post(
            "/vote/", json={"post_id": post_id, "reaction_type": "like"}
        )
    assert res.status_code == 201
    assert res.json()["message"] == "Successfully removed like reaction"
    reaction = _get_reaction(session, post_id, test_user["id"])
    assert reaction is None
    mock_queue.assert_called_once()
    mock_schedule.assert_called_once()


def test_vote_updates_reaction(
    authorized_client, test_posts, test_user, session, test_reaction
):
    """Test case for test vote updates reaction."""
    post_id = test_posts[3].id
    with _patch_email()[0] as mock_queue, _patch_email()[1] as mock_schedule:
        res = authorized_client.post(
            "/vote/", json={"post_id": post_id, "reaction_type": "love"}
        )
    assert res.status_code == 201
    assert res.json()["message"] == "Successfully updated reaction to love"
    reaction = _get_reaction(session, post_id, test_user["id"])
    assert reaction is not None
    assert reaction.reaction_type == models.ReactionType.LOVE
    mock_queue.assert_called_once()
    mock_schedule.assert_called_once()


def test_vote_post_non_exist(authorized_client):
    """Test case for test vote post non exist."""
    with _patch_email()[0], _patch_email()[1]:
        res = authorized_client.post(
            "/vote/", json={"post_id": 80000, "reaction_type": "like"}
        )
    assert res.status_code == 404
    assert "does not exist" in res.json()["detail"]


def test_vote_unauthorized_user(client, test_posts):
    """Test case for test vote unauthorized user."""
    post_id = test_posts[0].id
    res = client.post("/vote/", json={"post_id": post_id, "reaction_type": "like"})
    assert res.status_code == 401
    assert res.json()["detail"] == "Not authenticated"


@pytest.mark.parametrize("reaction_type", ["invalid", ""])
def test_vote_invalid_reaction_type(reaction_type, authorized_client, test_posts):
    """Test case for test vote invalid reaction type."""
    res = authorized_client.post(
        "/vote/",
        json={"post_id": test_posts[0].id, "reaction_type": reaction_type},
    )
    assert res.status_code == 422
    detail = res.json()["detail"]
    assert any("reaction_type" in err["loc"] for err in detail)


def test_vote_own_post(authorized_client, test_posts, test_user, session):
    """Test case for test vote own post."""
    post_id = test_posts[0].id
    with _patch_email()[0] as mock_queue, _patch_email()[1] as mock_schedule:
        res = authorized_client.post(
            "/vote/", json={"post_id": post_id, "reaction_type": "haha"}
        )
    assert res.status_code == 201
    reaction = _get_reaction(session, post_id, test_user["id"])
    assert reaction is not None
    mock_queue.assert_called_once()
    mock_schedule.assert_called_once()


def test_vote_other_user_post(authorized_client, test_posts, test_user, session):
    """Test case for test vote other user post."""
    post_id = test_posts[3].id
    with _patch_email()[0] as mock_queue, _patch_email()[1] as mock_schedule:
        res = authorized_client.post(
            "/vote/", json={"post_id": post_id, "reaction_type": "wow"}
        )
    assert res.status_code == 201
    reaction = _get_reaction(session, post_id, test_user["id"])
    assert reaction is not None
    mock_queue.assert_called_once()
    mock_schedule.assert_called_once()
