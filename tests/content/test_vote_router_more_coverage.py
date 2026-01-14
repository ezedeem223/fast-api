"""Additional coverage for vote router endpoints."""

from types import SimpleNamespace

from fastapi import BackgroundTasks

from app import schemas
from app.modules.posts.models import ReactionType
from app.routers import vote as vote_router


class DummyVoteService:
    """Stub vote service capturing inputs."""

    def __init__(self):
        self.seen = {}

    def vote(
        self,
        payload,
        current_user,
        background_tasks,
        queue_email_fn,
        schedule_email_fn,
        create_notification_fn,
        notification_manager,
    ):
        self.seen["vote"] = {
            "payload": payload,
            "user": current_user,
            "queue": queue_email_fn,
            "schedule": schedule_email_fn,
            "notify": create_notification_fn,
            "manager": notification_manager,
        }
        return {"result": "ok"}

    def remove_reaction(
        self,
        post_id,
        current_user,
        background_tasks,
        queue_email_fn,
        create_notification_fn,
    ):
        self.seen["remove"] = {
            "post_id": post_id,
            "user": current_user,
            "queue": queue_email_fn,
            "notify": create_notification_fn,
        }

    def get_vote_count(self, post_id):
        self.seen["count"] = post_id
        return {"post_id": post_id, "count": 5}

    def get_post_voters(self, post_id, current_user, skip, limit):
        self.seen["voters"] = {
            "post_id": post_id,
            "user": current_user,
            "skip": skip,
            "limit": limit,
        }
        return schemas.VotersListOut(voters=[], total_count=0)


def test_vote_router_calls_service_methods():
    """Exercise vote router paths using a stub service."""
    service = DummyVoteService()
    current_user = SimpleNamespace(id=1, email="v@example.com")
    background = BackgroundTasks()
    payload = schemas.ReactionCreate(
        post_id=123, reaction_type=ReactionType.LIKE
    )

    resp = vote_router.vote(
        request=SimpleNamespace(),
        vote=payload,
        background_tasks=background,
        service=service,
        current_user=current_user,
    )
    assert resp["result"] == "ok"
    assert service.seen["vote"]["payload"] == payload

    delete_resp = vote_router.remove_reaction(
        post_id=123,
        background_tasks=background,
        service=service,
        current_user=current_user,
    )
    assert delete_resp.status_code == 204
    assert service.seen["remove"]["post_id"] == 123

    count = vote_router.get_vote_count(post_id=123, service=service)
    assert count["count"] == 5

    voters = vote_router.get_post_voters(
        post_id=123, service=service, current_user=current_user, skip=1, limit=2
    )
    assert voters.total_count == 0
    assert service.seen["voters"]["skip"] == 1
