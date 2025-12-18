from types import SimpleNamespace
from datetime import datetime, timezone, timedelta

import pytest
from fastapi import HTTPException

from app import models
from app.services.local_economy_service import LocalEconomyService, ALLOWED_CATEGORIES
from app.services.support_service import SupportService
from app.services import reporting
from app.modules.moderation import service as moderation_service


def _user(session, email="u@example.com", verified=True):
    user = models.User(email=email, hashed_password="x", is_verified=verified)
    session.add(user)
    session.commit()
    session.refresh(user)
    return user


def test_local_economy_invalid_and_permissions(session):
    svc = LocalEconomyService(session)
    user = _user(session, verified=False)
    payload = SimpleNamespace(
        title="",
        description="",
        category="goods",
        latitude=0.0,
        longitude=0.0,
        price=-1,
    )
    # not verified -> 403
    with pytest.raises(HTTPException) as exc:
        svc.create_listing(current_user=user, payload=payload)
    assert exc.value.status_code == 403

    user.is_verified = True
    session.commit()
    # invalid title/price
    with pytest.raises(HTTPException) as exc:
        svc.create_listing(current_user=user, payload=payload)
    assert exc.value.status_code == 400

    # valid listing
    payload.title = "Bike"
    payload.price = 50
    listing = svc.create_listing(current_user=user, payload=payload)
    assert listing.id and listing.category in ALLOWED_CATEGORIES

    # self-inquiry forbidden
    with pytest.raises(HTTPException) as exc:
        svc.create_inquiry(listing_id=listing.id, current_user=user, message="hi")
    assert exc.value.status_code == 403


def test_support_happy_and_invalid(session):
    svc = SupportService(session)
    user = _user(session)

    ticket = svc.create_ticket(current_user=user, subject="help", description="need support")
    assert ticket.id and ticket.status == models.TicketStatus.OPEN

    resp = svc.add_response(current_user=user, ticket_id=ticket.id, content="got it")
    assert resp.id and resp.ticket_id == ticket.id

    with pytest.raises(HTTPException):
        svc.add_response(current_user=user, ticket_id=ticket.id, content="")


def test_reporting_invalid_and_duplicate(session):
    reporter = _user(session)
    post = models.Post(owner_id=reporter.id, title="t", content="c")
    session.add(post)
    session.commit()
    session.refresh(post)

    # invalid type -> both ids none raises 400
    with pytest.raises(HTTPException) as exc:
        reporting.submit_report(session, reporter, reason="r", post_id=None, comment_id=None)
    assert exc.value.status_code == 400

    reporting.submit_report(session, reporter, reason="valid", post_id=post.id)
    with pytest.raises(HTTPException) as exc:
        reporting.submit_report(session, reporter, reason="valid", post_id=post.id)
    assert exc.value.status_code == 409


def test_block_appeal_flow(session):
    blocker = _user(session, "blocker@example.com")
    blocked = _user(session, "blocked@example.com")
    block = models.Block(
        blocker_id=blocker.id,
        blocked_id=blocked.id,
        block_type=models.BlockType.FULL,
        ends_at=datetime.now(timezone.utc) + timedelta(days=1),
    )
    session.add(block)
    session.commit()
    session.refresh(block)

    appeal = moderation_service.submit_block_appeal(session, block_id=block.id, user_id=blocked.id, reason="please")
    assert appeal.status == models.AppealStatus.PENDING

    reviewed = moderation_service.review_block_appeal(session, appeal_id=appeal.id, approve=True, reviewer_id=blocker.id)
    assert reviewed.status == models.AppealStatus.APPROVED
