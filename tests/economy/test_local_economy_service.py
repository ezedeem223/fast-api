"""Test module for test session27 local economy."""
from types import SimpleNamespace

import pytest

from app import models
from app.services.local_economy_service import LocalEconomyService


def _service(session):
    """Helper for  service."""
    return LocalEconomyService(session)


def test_create_listing_success_and_validation(session):
    """Test case for test create listing success and validation."""
    user = models.User(email="loc27@example.com", hashed_password="x", is_verified=True)
    session.add(user)
    session.commit()
    session.refresh(user)

    svc = _service(session)
    listing = svc.create_listing(
        current_user=user,
        payload=SimpleNamespace(
            title="Bike",
            price=100,
            category="goods",
            description="mountain bike",
            currency="USD",
        ),
    )
    assert listing.title == "Bike"
    assert listing.price == 100

    with pytest.raises(Exception):
        svc.create_listing(
            current_user=user,
            payload=SimpleNamespace(title=" ", price=-1, category="invalid"),
        )


def test_create_inquiry_permissions(session):
    """Test case for test create inquiry permissions."""
    # Arrange: create seller, buyer, and listing.
    seller = models.User(
        email="seller27@example.com", hashed_password="x", is_verified=True
    )
    buyer = models.User(
        email="buyer27@example.com", hashed_password="x", is_verified=True
    )
    session.add_all([seller, buyer])
    session.commit()
    session.refresh(seller)
    session.refresh(buyer)

    listing = models.LocalMarketListing(
        seller_id=seller.id,
        title="Phone",
        description="smartphone",
        category="goods",
        latitude=0.0,
        longitude=0.0,
        price=50,
        currency="USD",
    )
    session.add(listing)
    session.commit()
    session.refresh(listing)

    svc = _service(session)
    # Act: buyer submits an inquiry.
    inquiry = svc.create_inquiry(
        listing_id=listing.id, current_user=buyer, message="Is it available?"
    )
    assert inquiry.listing_id == listing.id
    assert inquiry.buyer_id == buyer.id
    refreshed = session.get(models.LocalMarketListing, listing.id)
    # Assert: inquiries_count increments and seller cannot self-inquire.
    assert refreshed.inquiries_count == 1

    with pytest.raises(Exception):
        svc.create_inquiry(
            listing_id=listing.id, current_user=seller, message="self inquiry"
        )


def test_create_transaction(session):
    """Test case for test create transaction."""
    seller = models.User(
        email="seller27b@example.com", hashed_password="x", is_verified=True
    )
    buyer = models.User(
        email="buyer27b@example.com", hashed_password="x", is_verified=True
    )
    session.add_all([seller, buyer])
    session.commit()
    session.refresh(seller)
    session.refresh(buyer)

    listing = models.LocalMarketListing(
        seller_id=seller.id,
        title="Laptop",
        description="used",
        category="goods",
        latitude=0.0,
        longitude=0.0,
        price=500,
        currency="USD",
    )
    session.add(listing)
    session.commit()
    session.refresh(listing)

    svc = _service(session)
    txn = svc.create_transaction(listing_id=listing.id, current_user=buyer, quantity=2)
    assert txn.amount == 1000
    assert txn.seller_id == seller.id
    assert txn.buyer_id == buyer.id

    with pytest.raises(Exception):
        svc.create_transaction(listing_id=listing.id, current_user=seller, quantity=1)


def test_update_and_delete_listing(session):
    """Test case for test update and delete listing."""
    seller = models.User(
        email="seller27c@example.com", hashed_password="x", is_verified=True
    )
    session.add(seller)
    session.commit()
    session.refresh(seller)

    listing = models.LocalMarketListing(
        seller_id=seller.id,
        title="Tablet",
        description="old",
        category="goods",
        latitude=0.0,
        longitude=0.0,
        price=200,
        currency="USD",
    )
    session.add(listing)
    session.commit()
    svc = _service(session)

    updated = svc.update_listing(
        listing_id=listing.id,
        current_user=seller,
        payload=SimpleNamespace(title="Tablet Pro", price=250, description="updated"),
    )
    assert updated.title == "Tablet Pro"
    assert updated.price == 250

    resp = svc.delete_listing(listing_id=listing.id, current_user=seller)
    assert resp["message"]
    assert session.get(models.LocalMarketListing, listing.id) is None


def test_transaction_quantity_edge(session):
    """Test case for test transaction quantity edge."""
    seller = models.User(
        email="seller27d@example.com", hashed_password="x", is_verified=True
    )
    buyer = models.User(
        email="buyer27d@example.com", hashed_password="x", is_verified=True
    )
    session.add_all([seller, buyer])
    session.commit()
    listing = models.LocalMarketListing(
        seller_id=seller.id,
        title="Book",
        description="novel",
        category="goods",
        latitude=0.0,
        longitude=0.0,
        price=10,
        currency="USD",
    )
    session.add(listing)
    session.commit()
    svc = _service(session)

    txn = svc.create_transaction(listing_id=listing.id, current_user=buyer, quantity=3)
    assert txn.amount == 30

    with pytest.raises(Exception):
        svc.create_transaction(listing_id=listing.id, current_user=buyer, quantity=0)


def test_cooperative_transaction_flow(session):
    """Test case for test cooperative transaction flow."""
    owner = models.User(
        email="owner27coop@example.com", hashed_password="x", is_verified=True
    )
    member = models.User(
        email="member27coop@example.com", hashed_password="x", is_verified=True
    )
    session.add_all([owner, member])
    session.commit()
    cooperative = models.DigitalCooperative(
        name="coop", description="d", founder_id=owner.id, total_shares=100, revenue=0
    )
    coop_member = models.CooperativeMember(
        cooperative=cooperative,
        user_id=member.id,
        shares_owned=10,
        ownership_percentage=10,
    )
    session.add_all([cooperative, coop_member])
    session.commit()

    svc = _service(session)
    coop_txn = svc.create_cooperative_transaction(
        cooperative_id=cooperative.id,
        user_id=member.id,
        amount=100,
        notes="monthly",
    )
    assert coop_txn.amount == 100
    assert coop_txn.cooperative_id == cooperative.id
