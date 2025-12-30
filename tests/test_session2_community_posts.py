import asyncio
import warnings
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
from sqlalchemy.orm import Session

from app import models, schemas
from app.core.config import settings
from app.modules.posts.schemas import PostCreate
from app.modules.search.service import (
    update_search_statistics,
    update_search_suggestions,
)
from app.modules.utils import content as utils_content
from app.routers import session as session_router
from app.services.business.service import BusinessService
from app.services.comments.service import CommentService
from app.services.community.service import CommunityService
from app.services.posts.post_service import PostService
from app.services.users.service import UserService
from fastapi import BackgroundTasks, HTTPException

# Silence noisy bcrypt packaging warning from passlib during user creation hashing.
warnings.filterwarnings(
    "ignore",
    message=".*bcrypt version.*",
    module="passlib.handlers.bcrypt",
)


def _make_user(session: Session, email: str, verified: bool = True) -> models.User:
    user = models.User(email=email, hashed_password="hash", is_verified=verified)
    session.add(user)
    session.commit()
    session.refresh(user)
    return user


def _make_community(session: Session, owner: models.User, **kwargs) -> models.Community:
    community = models.Community(
        name=kwargs.get("name", "Test Community"),
        description=kwargs.get("description", "Desc"),
        owner_id=owner.id,
        is_private=kwargs.get("is_private", False),
        is_active=True,
    )
    session.add(community)
    session.commit()
    session.refresh(community)
    session.add(
        models.CommunityMember(
            community_id=community.id,
            user_id=owner.id,
            role=models.CommunityRole.OWNER,
        )
    )
    session.commit()
    return community


def test_community_create_requires_verified(session):
    service = CommunityService(session)
    unverified = _make_user(session, "nov@example.com", verified=False)
    payload = schemas.CommunityCreate(name="C1", description="D1")
    with pytest.raises(HTTPException) as exc:
        service.create_community(current_user=unverified, payload=payload)
    assert exc.value.status_code == 403


def test_community_post_empty_content(session):
    service = CommunityService(session)
    owner = _make_user(session, "owner@example.com")
    community = _make_community(session, owner)
    payload = PostCreate(title="t", content="   ")
    with pytest.raises(HTTPException) as exc:
        service.create_community_post(
            community_id=community.id, payload=payload, current_user=owner
        )
    assert exc.value.status_code == 400


def test_join_private_community_without_invite(session):
    service = CommunityService(session)
    owner = _make_user(session, "owner2@example.com")
    private_community = _make_community(session, owner, is_private=True)
    other = _make_user(session, "member@example.com")
    with pytest.raises(HTTPException) as exc:
        service.join_community(community_id=private_community.id, current_user=other)
    assert exc.value.status_code == 403


def test_invite_and_accept_flow(session):
    service = CommunityService(session)
    owner = _make_user(session, "owner3@example.com")
    member = _make_user(session, "member3@example.com")
    community = _make_community(session, owner)

    # Seed invitation manually to avoid model mismatch on message field
    invitation = models.CommunityInvitation(
        community_id=community.id, inviter_id=owner.id, invitee_id=member.id
    )
    session.add(invitation)
    session.commit()
    response = service.respond_to_invitation(
        invitation_id=invitation.id, current_user=member, accept=True
    )
    assert response["message"].startswith("Invitation accepted")

    # owner cannot leave own community
    with pytest.raises(HTTPException):
        service.leave_community(community_id=community.id, current_user=owner)

    # duplicate membership should raise
    with pytest.raises(HTTPException):
        service.join_community(community_id=community.id, current_user=member)


def test_invite_quota_exceeded(session, monkeypatch):
    service = CommunityService(session)
    owner = _make_user(session, "owner4@example.com")
    community = _make_community(session, owner)
    invitee = _make_user(session, "invitee-quota@example.com")
    new_invitee = _make_user(session, "invitee-new@example.com")
    monkeypatch.setattr(settings, "MAX_PENDING_INVITATIONS", 1)
    existing = models.CommunityInvitation(
        community_id=community.id,
        inviter_id=owner.id,
        invitee_id=invitee.id,
        status="pending",
    )
    session.add(existing)
    session.commit()
    new_invite = [
        MagicMock(
            community_id=community.id, invitee_id=new_invitee.id, user_id=owner.id
        )
    ]
    with pytest.raises(HTTPException) as exc:
        service.invite_members(
            community_id=community.id, invitations=new_invite, current_user=owner
        )
    assert exc.value.status_code == 400


def test_create_community_over_owner_limit(session, monkeypatch):
    service = CommunityService(session)
    monkeypatch.setattr(settings, "MAX_OWNED_COMMUNITIES", 0)
    owner = _make_user(session, "owner-limit@example.com")
    with pytest.raises(HTTPException):
        service.create_community(
            current_user=owner,
            payload=schemas.CommunityCreate(name="limit", description="d"),
        )


def test_community_post_rule_violation(session, monkeypatch):
    service = CommunityService(session)
    owner = _make_user(session, "owner-rule@example.com")
    community = _make_community(session, owner)
    # add a rule
    rule = models.CommunityRule(community_id=community.id, rule="forbid")
    session.add(rule)
    session.commit()
    monkeypatch.setattr(
        utils_content, "check_content_against_rules", lambda content, rules: False
    )
    with pytest.raises(HTTPException):
        service.create_community_post(
            community_id=community.id,
            payload=PostCreate(title="t", content="bad content"),
            current_user=owner,
        )


def test_community_vip_upgrade(session, monkeypatch):
    service = CommunityService(session)
    owner = _make_user(session, "owner-vip@example.com")
    community = _make_community(session, owner)
    monkeypatch.setattr("app.services.community.service.ACTIVITY_THRESHOLD_VIP", 0)
    member_user = _make_user(session, "member-vip@example.com")
    member = models.CommunityMember(
        community_id=community.id,
        user_id=member_user.id,
        role=models.CommunityRole.MEMBER,
    )
    session.add(member)
    session.commit()
    service.create_community_post(
        community_id=community.id,
        payload=PostCreate(title="vip", content="clean content"),
        current_user=member_user,
    )
    session.refresh(member)
    assert member.role == models.CommunityRole.VIP


def test_post_service_validation_and_analysis(session):
    service = PostService(session)
    tasks = BackgroundTasks()
    current_user = _make_user(session, "poster@example.com", verified=False)
    payload = PostCreate(title="Title", content="Hello world")

    with pytest.raises(HTTPException) as exc:
        service.create_post(
            background_tasks=tasks,
            payload=payload,
            current_user=current_user,
            queue_email_fn=lambda *a, **k: None,
            schedule_email_fn=lambda *a, **k: None,
            broadcast_fn=lambda msg: None,
            share_on_twitter_fn=lambda *a, **k: None,
            share_on_facebook_fn=lambda *a, **k: None,
            mention_notifier_fn=lambda *a, **k: None,
        )
    assert exc.value.status_code == 403

    verified_user = _make_user(session, "verified@example.com", verified=True)
    payload_empty = PostCreate(title="T2", content="   ")
    with pytest.raises(HTTPException) as exc2:
        service.create_post(
            background_tasks=tasks,
            payload=payload_empty,
            current_user=verified_user,
            queue_email_fn=lambda *a, **k: None,
            schedule_email_fn=lambda *a, **k: None,
            broadcast_fn=lambda msg: None,
            share_on_twitter_fn=lambda *a, **k: None,
            share_on_facebook_fn=lambda *a, **k: None,
            mention_notifier_fn=lambda *a, **k: None,
        )
    assert exc2.value.status_code in (400, 422)

    payload_analyze = PostCreate(title="T3", content="abc", analyze_content=True)
    with pytest.raises(HTTPException) as exc3:
        service.create_post(
            background_tasks=tasks,
            payload=payload_analyze,
            current_user=verified_user,
            queue_email_fn=lambda *a, **k: None,
            schedule_email_fn=lambda *a, **k: None,
            broadcast_fn=lambda msg: None,
            share_on_twitter_fn=lambda *a, **k: None,
            share_on_facebook_fn=lambda *a, **k: None,
            mention_notifier_fn=lambda *a, **k: None,
            analyze_content_fn=None,
        )
    assert exc3.value.status_code == 500

    poll_payload = schemas.PollCreate(
        title="P", description="D", options=["a", "b"], end_date=None
    )
    poll_post = service.create_poll_post(
        background_tasks=tasks,
        payload=poll_payload,
        current_user=verified_user,
        queue_email_fn=lambda *a, **k: None,
    )
    assert poll_post.is_poll is True

    # toggle archive/repost permissions
    archived = service.toggle_archive_post(
        post_id=poll_post.id, current_user=verified_user
    )
    assert archived.is_archived is True
    repost_toggled = service.toggle_allow_reposts(
        post_id=poll_post.id, current_user=verified_user
    )
    assert repost_toggled.allow_reposts is False

    # unauthorized delete
    with pytest.raises(HTTPException):
        service.delete_post(
            post_id=poll_post.id, current_user=_make_user(session, "other@example.com")
        )

    # analyze_existing_post unauthorized
    with pytest.raises(HTTPException):
        service.analyze_existing_post(
            post_id=poll_post.id,
            current_user=_make_user(session, "other2@example.com"),
            analyze_content_fn=lambda c: {
                "sentiment": {"sentiment": "pos", "score": 1},
                "suggestion": "ok",
            },
        )

    # analyze_existing_post happy path
    analyzed = service.analyze_existing_post(
        post_id=poll_post.id,
        current_user=verified_user,
        analyze_content_fn=lambda c: {
            "sentiment": {"sentiment": "pos", "score": 1},
            "suggestion": "ok",
        },
    )
    assert analyzed.sentiment == "pos"

    # update_post unauthorized and empty content paths
    with pytest.raises(HTTPException):
        service.update_post(
            post_id=poll_post.id,
            payload=PostCreate(title="t", content="   "),
            current_user=_make_user(session, "unauth@example.com"),
        )

    # report_content happy path
    report_result = service.report_content(
        current_user=verified_user, reason="spam", post_id=poll_post.id, comment_id=None
    )
    assert report_result


def test_comment_delete_requires_owner(session):
    post_owner = _make_user(session, "postowner@example.com")
    post = models.Post(
        owner_id=post_owner.id,
        title="p",
        content="c",
        is_safe_content=True,
    )
    session.add(post)
    session.commit()
    session.refresh(post)
    commenter = _make_user(session, "commenter@example.com")
    comment = models.Comment(
        owner_id=commenter.id, post_id=post.id, content="hi", is_deleted=False
    )
    session.add(comment)
    session.commit()
    service = CommentService(session)
    with pytest.raises(HTTPException) as exc:
        service.delete_comment(comment_id=comment.id, current_user=post_owner)
    assert exc.value.status_code == 403

    # update_comment rejects non-owner or past edit window
    with pytest.raises(HTTPException):
        service.update_comment(
            comment_id=comment.id,
            payload=schemas.CommentUpdate(content="edit"),
            current_user=post_owner,
            edit_window=None,
        )

    # Invalid media URLs should be rejected
    post.comment_count = 0
    session.commit()
    with pytest.raises(HTTPException):
        asyncio.run(
            service._validate_comment_content(
                schemas.CommentCreate(
                    content="bad",
                    post_id=post.id,
                    image_url="http://not-image",
                ),
                post,
            )
        )

    # like_comment happy path
    liked = service.like_comment(comment_id=comment.id)
    assert liked["message"].startswith("Comment liked")

    # list_comments hides flagged for non-moderator
    comment.is_flagged = True
    session.commit()
    comments = asyncio.run(
        service.list_comments(
            post_id=post.id,
            current_user=post_owner,  # not moderator
            sort_by="created_at",
            sort_order="desc",
            skip=0,
            limit=10,
        )
    )
    assert len(comments) == 0


def test_business_registration_and_transaction(session):
    biz_service = BusinessService(session)
    biz_user = _make_user(session, "biz@example.com")
    info = schemas.BusinessRegistration(
        business_name="Biz",
        business_registration_number="123",
        bank_account_info="bank",
    )
    registered = biz_service.register_business(
        current_user=biz_user, business_info=info
    )
    assert registered.user_type == models.UserType.BUSINESS

    # transaction should fail until verified_business flag set
    tx_payload = schemas.BusinessTransactionCreate(
        client_user_id=biz_user.id, amount=100
    )
    with pytest.raises(HTTPException):
        biz_service.create_transaction(current_user=biz_user, payload=tx_payload)

    # simulate verification success path
    biz_user.verification_status = models.VerificationStatus.APPROVED
    biz_user.is_verified_business = True
    session.commit()
    tx = biz_service.create_transaction(current_user=biz_user, payload=tx_payload)
    assert tx.amount == 100

    # verify_business success path
    async def fake_save(file):
        return "/tmp/path"

    verified = asyncio.run(
        biz_service.verify_business(
            current_user=biz_user,
            files=schemas.BusinessVerificationUpdate(
                id_document=MagicMock(),
                passport=MagicMock(),
                business_document=MagicMock(),
                selfie=MagicMock(),
            ),
            save_upload_fn=fake_save,
        )
    )
    assert verified.verification_status == models.VerificationStatus.PENDING

    # verify_business should fail for non-business user
    regular = _make_user(session, "reg@example.com")
    with pytest.raises(HTTPException):
        asyncio.run(
            biz_service.verify_business(
                current_user=regular,
                files=schemas.BusinessVerificationUpdate(
                    id_document=MagicMock(),
                    passport=MagicMock(),
                    business_document=MagicMock(),
                    selfie=MagicMock(),
                ),
                save_upload_fn=fake_save,
            )
        )


def test_user_service_language_and_duplicates(session):
    user_service = UserService(session)
    new_user = user_service.create_user(
        schemas.UserCreate(email="dup@example.com", password="pass", username="u1")
    )
    with pytest.raises(HTTPException):
        user_service.create_user(
            schemas.UserCreate(email="dup@example.com", password="pass", username="u2")
        )

    with pytest.raises(HTTPException):
        user_service.update_language_preferences(
            new_user,
            schemas.UserLanguageUpdate(preferred_language="xx", auto_translate=False),
        )

    with pytest.raises(HTTPException):
        user_service.update_privacy_settings(
            new_user,
            schemas.UserPrivacyUpdate(
                privacy_level=schemas.PrivacyLevel.CUSTOM, custom_privacy=None
            ),
        )

    # followers visibility private blocks others
    new_user.followers_visibility = "private"
    session.commit()
    other = _make_user(session, "viewer@example.com")
    with pytest.raises(HTTPException):
        user_service.get_user_followers(
            user_id=new_user.id,
            requesting_user=other,
            sort_by=schemas.SortOption.DATE,
            order="desc",
            skip=0,
            limit=10,
        )


def test_search_statistics_and_suggestions(session):
    user = _make_user(session, "searcher@example.com")
    update_search_statistics(session, user.id, "hello")
    update_search_statistics(session, user.id, "hello")
    stat = (
        session.query(models.SearchStatistics)
        .filter(
            models.SearchStatistics.user_id == user.id,
            models.SearchStatistics.term == "hello",
        )
        .first()
    )
    assert stat.searches == 2

    suggestion = models.SearchSuggestion(term="hello", usage_count=10)
    session.add(suggestion)
    session.commit()
    suggestions = update_search_suggestions(session)
    assert suggestions and suggestions[0].term == "hello"


def test_encrypted_session_routes(session):
    # Monkeypatch SignalProtocol to avoid heavy crypto and make deterministic keys
    class DummySignal:
        def __init__(self):
            self.root_key = b"r"
            self.chain_key = b"c"
            self.next_header_key = b"n"
            self.dh_pair = MagicMock()
            self.dh_pair.private_bytes_raw = MagicMock(return_value=b"x")

        def initial_key_exchange(self, other_public_key):
            return None

    session_router.crypto.SignalProtocol = DummySignal  # type: ignore

    user_service = UserService(session)
    u1 = user_service.create_user(
        schemas.UserCreate(email="sess1@example.com", password="pass", username="u1")
    )
    u2 = user_service.create_user(
        schemas.UserCreate(email="sess2@example.com", password="pass", username="u2")
    )
    u1.public_key = b"pub1"
    u2.public_key = b"pub2"
    session.commit()

    # create session
    created = session_router.create_encrypted_session(
        session=schemas.EncryptedSessionCreate(other_user_id=u2.id),
        db=session,
        current_user=u1,
    )
    assert created.other_user_id == u2.id

    # duplicate creation should fail
    with pytest.raises(HTTPException):
        session_router.create_encrypted_session(
            session=schemas.EncryptedSessionCreate(other_user_id=u2.id),
            db=session,
            current_user=u1,
        )

    # update session keys
    update_payload = SimpleNamespace(
        root_key=b"r2", chain_key=b"c2", next_header_key=b"n2", ratchet_key=b"rk2"
    )
    updated = session_router.update_encrypted_session(
        session_id=created.id,
        session_update=update_payload,
        db=session,
        current_user=u1,
    )
    assert updated.id == created.id

    with pytest.raises(HTTPException):
        session_router.create_encrypted_session(
            session=schemas.EncryptedSessionCreate(other_user_id=999),
            db=session,
            current_user=u1,
        )

    with pytest.raises(HTTPException):
        session_router.update_encrypted_session(
            session_id=999,
            session_update=update_payload,
            db=session,
            current_user=u1,
        )
