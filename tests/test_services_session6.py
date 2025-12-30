import pytest

from app import models, schemas
from app.services.comments import service as comment_service
from app.services.community import service as community_service
from app.services.posts.post_service import PostService
from app.services.users import service as users_service
from fastapi import HTTPException


def _user(session, email="u@example.com", verified=True):
    user = models.User(email=email, hashed_password="x", is_verified=verified)
    session.add(user)
    session.commit()
    session.refresh(user)
    return user


@pytest.mark.asyncio
async def test_list_comments_filters_flagged_for_regular_users(session):
    user = _user(session)
    post = models.Post(owner_id=user.id, title="t", content="c")
    session.add(post)
    session.commit()
    session.refresh(post)

    flagged = models.Comment(
        owner_id=user.id, post_id=post.id, content="bad link", is_flagged=True
    )
    visible = models.Comment(owner_id=user.id, post_id=post.id, content="ok")
    session.add_all([flagged, visible])
    session.commit()

    svc = comment_service.CommentService(session)
    comments = await svc.list_comments(
        post_id=post.id,
        current_user=user,
        sort_by="created_at",
        sort_order="desc",
        skip=0,
        limit=10,
    )
    returned_ids = {c.id for c in comments}
    assert visible.id in returned_ids
    assert flagged.id not in returned_ids


@pytest.mark.asyncio
async def test_list_comments_includes_flagged_for_moderators(session):
    user = _user(session)
    user.is_moderator = True
    post = models.Post(owner_id=user.id, title="t", content="c")
    session.add(post)
    session.commit()
    session.refresh(post)

    flagged = models.Comment(
        owner_id=user.id, post_id=post.id, content="flagged", is_flagged=True
    )
    session.add(flagged)
    session.commit()

    svc = comment_service.CommentService(session)
    comments = await svc.list_comments(
        post_id=post.id,
        current_user=user,
        sort_by="created_at",
        sort_order="desc",
        skip=0,
        limit=5,
    )
    assert any(c.id == flagged.id for c in comments)


def test_report_content_flags_comment(session):
    reporter = _user(session)
    post = models.Post(owner_id=reporter.id, title="t", content="c")
    session.add(post)
    session.commit()
    session.refresh(post)

    comment = models.Comment(
        owner_id=reporter.id, post_id=post.id, content="spam http://bad"
    )
    session.add(comment)
    session.commit()

    svc = comment_service.CommentService(session)
    report = svc.report_content(
        payload=schemas.ReportCreate(comment_id=comment.id, reason="spammy"),
        current_user=reporter,
    )
    session.refresh(comment)
    assert comment.is_flagged is True
    assert report.reported_user_id == reporter.id


def test_comment_soft_delete_marks_record(session):
    owner = _user(session)
    post = models.Post(owner_id=owner.id, title="t", content="c")
    comment = models.Comment(owner_id=owner.id, post=post, content="to delete")
    session.add_all([post, comment])
    session.commit()

    svc = comment_service.CommentService(session)
    result = svc.delete_comment(comment_id=comment.id, current_user=owner)
    session.refresh(comment)
    assert result["message"]
    assert comment.is_deleted is True
    assert comment.content == "[Deleted]"


def test_set_best_answer_requires_owner(session):
    owner = _user(session)
    other = _user(session, email="other@example.com")
    post = models.Post(owner_id=owner.id, title="t", content="c")
    comment = models.Comment(owner_id=other.id, post=post, content="answer")
    session.add_all([post, comment])
    session.commit()

    svc = comment_service.CommentService(session)
    with pytest.raises(HTTPException) as exc:
        svc.set_best_answer(comment_id=comment.id, current_user=other)
    assert exc.value.status_code == 403


def test_create_user_duplicate_email_raises(session):
    svc = users_service.UserService(session)
    svc.create_user(
        schemas.UserCreate(email="dup@example.com", password="pw", username="user1")
    )
    with pytest.raises(HTTPException):
        svc.create_user(
            schemas.UserCreate(email="dup@example.com", password="pw", username="user2")
        )


def test_privacy_custom_requires_payload(session):
    svc = users_service.UserService(session)
    user = svc.create_user(
        schemas.UserCreate(email="p@example.com", password="pw", username="user3")
    )
    with pytest.raises(HTTPException):
        svc.update_privacy_settings(
            user,
            schemas.UserPrivacyUpdate(privacy_level=schemas.PrivacyLevel.CUSTOM),
        )


def test_followers_settings_persist(session):
    svc = users_service.UserService(session)
    user = svc.create_user(
        schemas.UserCreate(email="f@example.com", password="pw", username="user4")
    )
    settings = schemas.UserFollowersSettings(
        followers_visibility="private",
        followers_custom_visibility={"allowed_users": [user.id]},
        followers_sort_preference=schemas.SortOption.DATE_ASC,
    )
    saved = svc.update_followers_settings(user, settings)
    assert saved.followers_visibility == "private"
    assert saved.followers_custom_visibility["allowed_users"] == [user.id]


def test_invite_members_skips_duplicates(session):
    owner = _user(session)
    invitee = _user(session, email="invitee@example.com")
    community = models.Community(name="c", description="d", owner_id=owner.id)
    membership = models.CommunityMember(
        community=community, user=owner, role=models.CommunityRole.OWNER
    )
    session.add_all([community, membership])
    session.commit()

    svc = community_service.CommunityService(session)
    first_batch = svc.invite_members(
        community_id=community.id,
        invitations=[
            schemas.CommunityInvitationCreate(
                community_id=community.id, invitee_id=invitee.id, user_id=owner.id
            )
        ],
        current_user=owner,
    )
    second_batch = svc.invite_members(
        community_id=community.id,
        invitations=[
            schemas.CommunityInvitationCreate(
                community_id=community.id, invitee_id=invitee.id, user_id=owner.id
            )
        ],
        current_user=owner,
    )
    assert len(first_batch) == 1
    assert second_batch == []


def test_vote_in_poll_updates_existing_vote(session):
    voter = _user(session)
    post = models.Post(owner_id=voter.id, title="poll", content="c", is_poll=True)
    session.add(post)
    session.commit()
    session.refresh(post)

    poll = models.Poll(post_id=post.id)
    option_a = models.PollOption(post_id=post.id, option_text="A")
    option_b = models.PollOption(post_id=post.id, option_text="B")
    session.add_all([poll, option_a, option_b])
    session.commit()
    session.refresh(option_a)
    session.refresh(option_b)

    service = PostService(session)
    service.vote_in_poll(post_id=post.id, option_id=option_a.id, current_user=voter)
    service.vote_in_poll(post_id=post.id, option_id=option_b.id, current_user=voter)

    votes = session.query(models.PollVote).filter_by(post_id=post.id).all()
    assert len(votes) == 1
    assert votes[0].option_id == option_b.id
