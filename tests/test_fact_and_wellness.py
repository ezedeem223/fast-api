from app.modules.fact_checking.models import FactCheckStatus
from app.modules.learning.models import (
    Certificate,
    LearningEnrollment,
    LearningModule,
    LearningPath,
)
from app.modules.local_economy.models import (
    CooperativeMember,
    CooperativeTransaction,
    DigitalCooperative,
    LocalMarketInquiry,
    LocalMarketListing,
    LocalMarketTransaction,
)
from app.modules.marketplace.models import (
    ContentListing,
    ContentPurchase,
    ContentReview,
    ContentSubscription,
)


def test_fact_checking_flow_updates_scores_and_status(authorized_client):
    submit_res = authorized_client.post(
        "/fact-checking/submit",
        json={
            "claim": "The sky appears blue on clear days.",
            "description": "Basic physics claim",
            "evidence_links": ["https://example.com/blue-sky"],
        },
    )
    assert submit_res.status_code == 200
    fact_id = submit_res.json()["id"]

    verify_res = authorized_client.post(
        f"/fact-checking/verify/{fact_id}",
        json={
            "verdict": FactCheckStatus.VERIFIED.value,
            "confidence_score": 0.9,
            "explanation": "Observed phenomenon",
            "evidence": ["https://example.com/science"],
        },
    )
    assert verify_res.status_code == 200

    vote_res = authorized_client.post(
        f"/fact-checking/vote/{fact_id}", json={"vote_type": "support"}
    )
    assert vote_res.status_code == 200

    correction_res = authorized_client.post(
        f"/fact-checking/correct/{fact_id}",
        json={"corrected_claim": "Daytime sky is blue", "reason": "Clarity"},
    )
    assert correction_res.status_code == 200

    fact_res = authorized_client.get(f"/fact-checking/facts/{fact_id}")
    assert fact_res.status_code == 200
    fact_body = fact_res.json()
    assert fact_body["status"] == FactCheckStatus.VERIFIED.value
    assert fact_body["verification_score"] > 0
    assert fact_body["community_consensus"] >= 1.0
    assert fact_body["claim"] == "Daytime sky is blue"

    list_res = authorized_client.get(
        "/fact-checking/facts", params={"status": FactCheckStatus.VERIFIED.value}
    )
    assert any(item["id"] == fact_id for item in list_res.json())

    search_res = authorized_client.get("/fact-checking/search", params={"q": "sky"})
    assert any(item["id"] == fact_id for item in search_res.json())


def test_wellness_endpoints_create_metrics_and_modes(authorized_client):
    metrics_res = authorized_client.get("/wellness/metrics")
    assert metrics_res.status_code == 200
    metrics = metrics_res.json()
    assert "wellness_score" in metrics
    assert "usage_pattern" in metrics

    goal_res = authorized_client.post(
        "/wellness/goals", json={"goal_type": "reduce_usage", "target_value": 120}
    )
    assert goal_res.status_code == 200
    assert "id" in goal_res.json()

    dnd_res = authorized_client.post(
        "/wellness/do-not-disturb", json={"duration_minutes": 30}
    )
    assert dnd_res.status_code == 200
    assert dnd_res.json()["do_not_disturb"] is True

    mh_res = authorized_client.post(
        "/wellness/mental-health-mode", json={"duration_minutes": 15}
    )
    assert mh_res.status_code == 200
    assert mh_res.json()["mental_health_mode"] is True


def test_new_domain_models_persist_and_link(session, test_user, test_user2):
    listing = LocalMarketListing(
        seller_id=test_user.id,
        title="3D Printing",
        description="Offer 3D printing services",
        category="services",
        latitude=24.7136,
        longitude=46.6753,
        price=25.0,
    )
    session.add(listing)
    session.flush()

    inquiry = LocalMarketInquiry(
        listing_id=listing.id,
        buyer_id=test_user2.id,
        message="Can you print a prototype?",
    )
    transaction = LocalMarketTransaction(
        listing_id=listing.id,
        buyer_id=test_user2.id,
        seller_id=test_user.id,
        amount=50.0,
        quantity=2,
    )
    coop = DigitalCooperative(
        name="Makers Guild",
        description="Local maker collective",
        founder_id=test_user.id,
        total_shares=100,
    )
    session.add_all([inquiry, transaction, coop])
    session.flush()

    member = CooperativeMember(
        cooperative_id=coop.id,
        user_id=test_user2.id,
        shares_owned=10,
        ownership_percentage=10.0,
    )
    coop_tx = CooperativeTransaction(
        cooperative_id=coop.id, amount=125.0, description="Initial funding"
    )
    session.add_all([member, coop_tx])

    content = ContentListing(
        creator_id=test_user.id,
        title="UX Course",
        description="Learn UX in 7 days",
        content_type="course",
        price=99.0,
    )
    session.add(content)
    session.flush()

    purchase = ContentPurchase(
        listing_id=content.id,
        buyer_id=test_user2.id,
        amount=99.0,
        commission=9.9,
        creator_earnings=89.1,
    )
    subscription = ContentSubscription(
        creator_id=test_user.id, subscriber_id=test_user2.id, monthly_price=15.0
    )
    review = ContentReview(
        listing_id=content.id, reviewer_id=test_user2.id, rating=4.5, comment="Great"
    )
    session.add_all([purchase, subscription, review])

    path = LearningPath(
        title="Backend Foundations",
        description="APIs and databases",
        category="engineering",
        difficulty_level="beginner",
    )
    session.add(path)
    session.flush()

    module = LearningModule(
        path_id=path.id, title="Intro to APIs", content="REST basics", order=1
    )
    enrollment = LearningEnrollment(
        user_id=test_user.id, path_id=path.id, progress_percentage=20.0
    )
    certificate = Certificate(
        user_id=test_user.id,
        path_id=path.id,
        certificate_number="CERT-12345",
        issued_by="Academy",
    )
    session.add_all([module, enrollment, certificate])
    session.commit()

    assert inquiry.listing_id == listing.id
    assert transaction.seller_id == test_user.id
    assert member.cooperative_id == coop.id
    assert purchase.listing_id == content.id
    assert subscription.subscriber_id == test_user2.id
    assert module.path_id == path.id
    assert certificate.certificate_number == "CERT-12345"
