import pytest

from app import models
from app.modules.social.economy_service import SocialEconomyService
from app.services.posts.post_service import PostService


def test_quality_and_engagement_scores(session):
    svc = SocialEconomyService(session)
    low = svc.calculate_quality_score("short")
    high = svc.calculate_quality_score("word " * 30)
    assert high > low

    post = models.Post(title="t", content="content", owner_id=1)
    session.add(post)
    session.commit()
    session.refresh(post)
    e0 = svc._engagement_from_counts(0, 0)
    e1 = svc._engagement_from_counts(3, 2)
    assert e1 > e0


def test_update_post_score_adds_credits(session):
    user = models.User(email="score24@example.com", hashed_password="x", is_verified=True, social_credits=0)
    post = models.Post(title="t", content="good content " * 10, owner=user)
    session.add_all([user, post])
    session.commit()
    session.refresh(post)

    svc = SocialEconomyService(session)
    total = svc.update_post_score(post.id)
    session.refresh(user)
    assert total > 0
    assert user.social_credits > 0
    assert post.score == total


def test_bulk_update_post_scores(session):
    user = models.User(email="bulk24@example.com", hashed_password="x", is_verified=True, social_credits=0)
    post1 = models.Post(title="t1", content="c1 " * 20, owner=user)
    post2 = models.Post(title="t2", content="c2 " * 20, owner=user)
    session.add_all([user, post1, post2])
    session.commit()
    session.add(models.Reaction(post_id=post1.id, user_id=user.id, reaction_type="like"))
    session.commit()

    svc = SocialEconomyService(session)
    scores = svc.bulk_update_post_scores([post1.id, post2.id])
    assert set(scores.keys()) == {post1.id, post2.id}
    assert all(val > 0 for val in scores.values())
    session.refresh(user)
    assert user.social_credits > 0


@pytest.mark.filterwarnings("ignore:Coercing Subquery object")
def test_recommendations_flow_prioritizes_followed(session, monkeypatch):
    current_user = models.User(email="cur24@example.com", hashed_password="x", is_verified=True)
    followed_user = models.User(email="followed24@example.com", hashed_password="x", is_verified=True)
    other_user = models.User(email="other24@example.com", hashed_password="x", is_verified=True)
    session.add_all([current_user, followed_user, other_user])
    session.commit()
    session.refresh(current_user)
    session.add(models.Follow(follower_id=current_user.id, followed_id=followed_user.id))
    session.commit()

    post_followed = models.Post(title="pf", content="c " * 10, owner=followed_user)
    post_other = models.Post(title="po", content="c " * 10, owner=other_user)
    session.add_all([post_followed, post_other])
    session.commit()
    session.add(models.Comment(owner_id=followed_user.id, post_id=post_followed.id, content="hi", language="en"))
    session.add(models.Reaction(user_id=followed_user.id, post_id=post_followed.id, reaction_type="like"))
    session.commit()

    service = PostService(session)
    # keep response simple
    monkeypatch.setattr(service, "_prepare_post_response", lambda post, owner=None: post)
    # Align expected attribute for COUNT in recommendations
    setattr(models.Vote, "id", models.Vote.post_id)
    recs = service.get_recommendations(current_user=current_user, limit_followed=5, limit_others=5)

    assert post_followed in recs
    assert post_other in recs
    # followed user's post should appear first
    assert recs[0].owner_id == followed_user.id
