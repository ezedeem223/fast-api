import pytest

from app import models


def test_local_market_listing_inquiry_and_transaction(session, test_user, test_user2):
    listing = models.LocalMarketListing(
        seller_id=test_user["id"],
        title="Neighborhood Skill",
        description="Will help set up home network",
        category="skills",
        latitude=24.0,
        longitude=54.0,
        price=50.0,
        currency="USD",
    )
    session.add(listing)
    session.commit()
    session.refresh(listing)

    inquiry = models.LocalMarketInquiry(
        listing_id=listing.id,
        buyer_id=test_user2["id"],
        message="Interested in booking this weekend",
    )
    session.add(inquiry)
    session.commit()
    session.refresh(inquiry)

    transaction = models.LocalMarketTransaction(
        listing_id=listing.id,
        buyer_id=test_user2["id"],
        seller_id=test_user["id"],
        amount=100.0,
        quantity=2,
    )
    session.add(transaction)
    session.commit()
    session.refresh(transaction)
    session.refresh(listing)

    assert listing.id == inquiry.listing_id
    assert listing.id == transaction.listing_id
    assert transaction.seller_id == test_user["id"]
    assert transaction.buyer_id == test_user2["id"]
    assert len(listing.inquiries) == 1
    assert listing.inquiries[0].id == inquiry.id
    assert len(listing.transactions) == 1
    assert listing.transactions[0].amount == pytest.approx(100.0)


def test_digital_cooperative_membership_and_revenue(session, test_user, test_user2):
    coop = models.DigitalCooperative(
        name="Local Builders Coop",
        description="Collaborative ownership for neighborhood projects",
        founder_id=test_user["id"],
        total_shares=100,
        members_count=0,
        revenue=0.0,
    )
    session.add(coop)
    session.commit()
    session.refresh(coop)

    member_primary = models.CooperativeMember(
        cooperative_id=coop.id,
        user_id=test_user["id"],
        shares_owned=60,
        ownership_percentage=60.0,
    )
    member_secondary = models.CooperativeMember(
        cooperative_id=coop.id,
        user_id=test_user2["id"],
        shares_owned=40,
        ownership_percentage=40.0,
    )
    session.add_all([member_primary, member_secondary])
    session.commit()
    session.refresh(member_primary)
    session.refresh(member_secondary)

    revenue_tx = models.CooperativeTransaction(
        cooperative_id=coop.id, amount=500.0, description="Quarterly payout"
    )
    session.add(revenue_tx)
    session.commit()
    session.refresh(revenue_tx)
    session.refresh(coop)

    member_user_ids = {member.user_id for member in coop.members}
    assert member_user_ids == {test_user["id"], test_user2["id"]}
    assert pytest.approx(
        sum(member.ownership_percentage for member in coop.members)
    ) == 100.0
    assert coop.transactions[0].amount == pytest.approx(500.0)
