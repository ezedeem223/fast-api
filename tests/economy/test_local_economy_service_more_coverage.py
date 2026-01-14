"""Additional coverage for LocalEconomyService error branches."""

from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from app import models
from app.services.local_economy_service import LocalEconomyService


def _user(session, email, verified=True):
    """Helper to create a user."""
    user = models.User(email=email, hashed_password="x", is_verified=verified)
    session.add(user)
    session.commit()
    session.refresh(user)
    return user


def _listing(session, seller):
    """Helper to create a listing."""
    listing = models.LocalMarketListing(
        seller_id=seller.id,
        title="Item",
        description="desc",
        category="goods",
        latitude=0.0,
        longitude=0.0,
        price=10,
        currency="USD",
    )
    session.add(listing)
    session.commit()
    session.refresh(listing)
    return listing


def _cooperative(session, founder):
    """Helper to create a cooperative."""
    cooperative = models.DigitalCooperative(
        name="coop",
        description="d",
        founder_id=founder.id,
        total_shares=100,
        revenue=0,
    )
    session.add(cooperative)
    session.commit()
    session.refresh(cooperative)
    return cooperative


def test_local_economy_requires_user_and_inquiry_errors(session):
    """Cover missing auth and inquiry validation branches."""
    svc = LocalEconomyService(session)

    with pytest.raises(HTTPException) as exc:
        svc.create_listing(
            current_user=None,
            payload=SimpleNamespace(title="Item", price=10, category="goods"),
        )
    assert exc.value.status_code == 401
    assert exc.value.detail == "Auth required"

    buyer = _user(session, "buyer_le@example.com")
    with pytest.raises(HTTPException) as exc:
        svc.create_inquiry(listing_id=999, current_user=buyer, message="hi")
    assert exc.value.status_code == 404
    assert exc.value.detail == "Listing not found"

    seller = _user(session, "seller_le@example.com")
    listing = _listing(session, seller)
    with pytest.raises(HTTPException) as exc:
        svc.create_inquiry(listing_id=listing.id, current_user=buyer, message=" ")
    assert exc.value.status_code == 400
    assert exc.value.detail == "Message is required"


def test_local_economy_transaction_update_delete_errors(session):
    """Cover missing transaction/update/delete branches."""
    svc = LocalEconomyService(session)

    buyer = _user(session, "buyer_tx@example.com")
    with pytest.raises(HTTPException) as exc:
        svc.create_transaction(listing_id=999, current_user=buyer, quantity=1)
    assert exc.value.status_code == 404
    assert exc.value.detail == "Listing not found"

    seller = _user(session, "seller_tx@example.com")
    listing = _listing(session, seller)
    other = _user(session, "other_tx@example.com")

    with pytest.raises(HTTPException) as exc:
        svc.update_listing(
            listing_id=listing.id,
            current_user=other,
            payload=SimpleNamespace(title="New", price=20, description="d"),
        )
    assert exc.value.status_code == 403
    assert exc.value.detail == "Not authorized to update listing"

    with pytest.raises(HTTPException) as exc:
        svc.update_listing(
            listing_id=999,
            current_user=seller,
            payload=SimpleNamespace(title="New", price=20, description="d"),
        )
    assert exc.value.status_code == 404
    assert exc.value.detail == "Listing not found"

    with pytest.raises(HTTPException) as exc:
        svc.update_listing(
            listing_id=listing.id,
            current_user=seller,
            payload=SimpleNamespace(title="", price=0, description="bad"),
        )
    assert exc.value.status_code == 400
    assert exc.value.detail == "Invalid update data"

    with pytest.raises(HTTPException) as exc:
        svc.delete_listing(listing_id=999, current_user=seller)
    assert exc.value.status_code == 404
    assert exc.value.detail == "Listing not found"

    with pytest.raises(HTTPException) as exc:
        svc.delete_listing(listing_id=listing.id, current_user=other)
    assert exc.value.status_code == 403
    assert exc.value.detail == "Not authorized to delete listing"


def test_local_economy_cooperative_errors(session):
    """Cover cooperative transaction validation branches."""
    svc = LocalEconomyService(session)
    founder = _user(session, "founder_le@example.com")

    with pytest.raises(HTTPException) as exc:
        svc.create_cooperative_transaction(
            cooperative_id=1, user_id=founder.id, amount=0
        )
    assert exc.value.status_code == 400
    assert exc.value.detail == "Amount must be positive"

    with pytest.raises(HTTPException) as exc:
        svc.create_cooperative_transaction(
            cooperative_id=999, user_id=founder.id, amount=10
        )
    assert exc.value.status_code == 404
    assert exc.value.detail == "Cooperative not found"

    coop = _cooperative(session, founder)
    with pytest.raises(HTTPException) as exc:
        svc.create_cooperative_transaction(
            cooperative_id=coop.id, user_id=founder.id, amount=10
        )
    assert exc.value.status_code == 403
    assert exc.value.detail == "Not a cooperative member"
