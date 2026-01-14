"""Test module for test session6 vote service."""
import pytest

from app import models, schemas
from app.modules.utils.security import hash as hash_password
from app.services.posts.vote_service import VoteService
from fastapi import BackgroundTasks, HTTPException


def _user(session, email="voter@example.com"):
    """Helper for  user."""
    u = models.User(
        email=email,
        hashed_password=hash_password("x"),
        is_verified=True,
    )
    session.add(u)
    session.commit()
    session.refresh(u)
    return u


def _post(session, owner):
    """Helper for  post."""
    p = models.Post(owner_id=owner.id, title="t", content="c", is_safe_content=True)
    session.add(p)
    session.commit()
    session.refresh(p)
    return p


class _StubNotify:
    """Test class for _StubNotify."""
    def __init__(self):
        self.emails = []
        self.notifications = []
        self.broadcasts = []

    def queue_email_fn(self, tasks, to, subject, body):
        self.emails.append((to, subject))

    def schedule_email_fn(self, tasks, to, subject, body):
        self.emails.append((to, subject))

    def create_notification_fn(self, db, user_id, title, path, kind, ref_id):
        self.notifications.append((user_id, kind))

    class Manager:
        def __init__(self, outer):
            self.outer = outer

        def broadcast(self, msg):
            self.outer.broadcasts.append(msg)


@pytest.mark.asyncio
async def test_vote_add_update_remove(session, monkeypatch):
    """Test case for test vote add update remove."""
    service = VoteService(session)
    owner = _user(session, "owner@example.com")
    voter = _user(session, "voter@example.com")
    post = _post(session, owner)
    tasks = BackgroundTasks()
    stub = _StubNotify()
    manager = stub.Manager(stub)

    payload = schemas.ReactionCreate(
        post_id=post.id, reaction_type=models.ReactionType.LIKE
    )
    resp_add = service.vote(
        payload=payload,
        current_user=voter,
        background_tasks=tasks,
        queue_email_fn=stub.queue_email_fn,
        schedule_email_fn=stub.schedule_email_fn,
        create_notification_fn=stub.create_notification_fn,
        notification_manager=manager,
    )
    assert "added" in resp_add["message"]
    assert stub.emails and stub.notifications

    payload_change = schemas.ReactionCreate(
        post_id=post.id, reaction_type=models.ReactionType.LOVE
    )
    resp_change = service.vote(
        payload=payload_change,
        current_user=voter,
        background_tasks=tasks,
        queue_email_fn=stub.queue_email_fn,
        schedule_email_fn=stub.schedule_email_fn,
        create_notification_fn=stub.create_notification_fn,
        notification_manager=manager,
    )
    assert "updated" in resp_change["message"]

    # same reaction toggles removal
    resp_remove = service.vote(
        payload=payload_change,
        current_user=voter,
        background_tasks=tasks,
        queue_email_fn=stub.queue_email_fn,
        schedule_email_fn=stub.schedule_email_fn,
        create_notification_fn=stub.create_notification_fn,
        notification_manager=manager,
    )
    assert "removed" in resp_remove["message"]
    assert (
        session.query(models.Reaction)
        .filter_by(post_id=post.id, user_id=voter.id)
        .first()
        is None
    )

    with pytest.raises(HTTPException):
        service.vote(
            payload=schemas.ReactionCreate(
                post_id=999999, reaction_type=models.ReactionType.LIKE
            ),
            current_user=voter,
            background_tasks=tasks,
        )


def test_remove_reaction_and_permissions(session):
    """Test case for test remove reaction and permissions."""
    service = VoteService(session)
    owner = _user(session, "owner2@example.com")
    voter = _user(session, "voter2@example.com")
    other = _user(session, "other@example.com")
    post = _post(session, owner)
    tasks = BackgroundTasks()

    reaction = models.Reaction(
        user_id=voter.id, post_id=post.id, reaction_type=models.ReactionType.LIKE
    )
    session.add(reaction)
    session.commit()

    # wrong user -> 404 because reaction not found for that user
    with pytest.raises(HTTPException) as exc:
        service.remove_reaction(
            post_id=post.id, current_user=other, background_tasks=tasks
        )
    assert exc.value.status_code == 404

    service.remove_reaction(post_id=post.id, current_user=voter, background_tasks=tasks)
    assert (
        session.query(models.Reaction)
        .filter_by(post_id=post.id, user_id=voter.id)
        .first()
        is None
    )


def test_get_post_voters_permissions(session):
    """Test case for test get post voters permissions."""
    service = VoteService(session)
    owner = _user(session, "owner3@example.com")
    moderator = _user(session, "mod@example.com")
    moderator.is_moderator = True
    session.commit()
    other = _user(session, "other3@example.com")
    # ensure username attribute exists for schema validation
    owner.username = "owner3"
    moderator.username = "mod"
    other.username = "other3"
    post = _post(session, owner)

    vote = models.Vote(user_id=other.id, post_id=post.id)
    session.add(vote)
    session.commit()

    # patch VoterOut to tolerate missing persisted username by deriving from email
    import app.services.posts.vote_service as vote_service_mod

    original_validate = vote_service_mod.schemas.VoterOut.model_validate

    def _safe_validate(voter):
        if not getattr(voter, "username", None):
            voter.username = voter.email.split("@")[0]
        return original_validate(voter)

    vote_service_mod.schemas.VoterOut.model_validate = staticmethod(_safe_validate)

    voters_owner = service.get_post_voters(
        post_id=post.id, current_user=owner, skip=0, limit=10
    )
    assert voters_owner.total_count == 1

    voters_mod = service.get_post_voters(
        post_id=post.id, current_user=moderator, skip=0, limit=10
    )
    assert voters_mod.total_count == 1

    with pytest.raises(HTTPException) as exc:
        service.get_post_voters(post_id=post.id, current_user=other, skip=0, limit=10)
    assert exc.value.status_code == 403

    vote_service_mod.schemas.VoterOut.model_validate = original_validate
