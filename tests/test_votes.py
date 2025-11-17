import pytest
from app import models
from unittest.mock import patch


@pytest.fixture()
def test_reaction(test_posts, session, test_user):
    reaction = models.Reaction(
        post_id=test_posts[3].id,
        user_id=test_user["id"],
        reaction_type=models.ReactionType.LIKE.value,
    )
    session.add(reaction)
    session.commit()
    return reaction


def _patch_email():
    return patch("app.routers.vote.queue_email_notification"), patch(
        "app.routers.vote.schedule_email_notification"
    )


def _get_reaction(session, post_id, user_id):
    return (
        session.query(models.Reaction)
        .filter(
            models.Reaction.post_id == post_id,
            models.Reaction.user_id == user_id,
        )
        .first()
    )


def test_vote_on_post(authorized_client, test_posts, test_user, session):
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
    with _patch_email()[0], _patch_email()[1]:
        res = authorized_client.post(
            "/vote/", json={"post_id": 80000, "reaction_type": "like"}
        )
    assert res.status_code == 404


def test_vote_unauthorized_user(client, test_posts):
    post_id = test_posts[0].id
    res = client.post("/vote/", json={"post_id": post_id, "reaction_type": "like"})
    assert res.status_code == 401


@pytest.mark.parametrize("reaction_type", ["invalid", ""])
def test_vote_invalid_reaction_type(reaction_type, authorized_client, test_posts):
    res = authorized_client.post(
        "/vote/",
        json={"post_id": test_posts[0].id, "reaction_type": reaction_type},
    )
    assert res.status_code == 422


def test_vote_own_post(authorized_client, test_posts, test_user, session):
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
