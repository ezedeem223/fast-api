
from app import models
from app.modules.fact_checking.models import FactCheckStatus
from app.modules.support.models import TicketStatus, TicketResponse as TicketResponseModel


def test_fact_checking_flow_with_votes_and_warnings(session, test_user, test_user2, test_post):
    fact = models.Fact(
        claim="Coffee reduces stress",
        source_post_id=test_post["id"],
        submitter_id=test_user["id"],
        status=FactCheckStatus.PENDING,
        evidence_links=["http://example.com/study"],
    )
    session.add(fact)
    session.commit()
    session.refresh(fact)

    verification = models.FactVerification(
        fact_id=fact.id,
        verifier_id=test_user2["id"],
        verdict=FactCheckStatus.VERIFIED,
        confidence_score=0.82,
        explanation="Controlled trial with 200 participants",
    )
    correction = models.FactCorrection(
        fact_id=fact.id,
        corrector_id=test_user2["id"],
        original_claim="Coffee reduces stress",
        corrected_claim="Moderate coffee intake correlates with lower stress markers",
        reason="Clarify correlation vs causation",
    )
    badge = models.CredibilityBadge(
        fact_id=fact.id,
        badge_type="verified_health",
        issuer_id=test_user["id"],
    )
    vote_support = models.FactVote(
        fact_id=fact.id, voter_id=test_user2["id"], vote_type="support"
    )
    warning = models.MisinformationWarning(
        post_id=test_post["id"], warning_type="misleading", related_fact_id=fact.id
    )

    session.add_all([verification, correction, badge, vote_support, warning])
    session.commit()
    session.refresh(fact)

    assert fact.verifications[0].verdict == FactCheckStatus.VERIFIED
    assert fact.corrections[0].corrected_claim.startswith("Moderate coffee intake")
    assert fact.credibility_badges[0].badge_type == "verified_health"
    assert fact.votes[0].vote_type == "support"
    assert warning.related_fact_id == fact.id


def test_support_ticket_lifecycle_and_cascade(session, test_user, test_user2):
    ticket = models.SupportTicket(
        user_id=test_user["id"],
        subject="Cannot upload media",
        description="Uploads fail with 500 error",
        status=TicketStatus.OPEN,
    )
    session.add(ticket)
    session.commit()
    session.refresh(ticket)

    response_user = TicketResponseModel(
        ticket_id=ticket.id,
        user_id=test_user["id"],
        content="Additional logs attached",
    )
    response_staff = TicketResponseModel(
        ticket_id=ticket.id,
        user_id=test_user2["id"],
        content="Issue acknowledged, investigating",
    )
    session.add_all([response_user, response_staff])
    session.commit()

    assert len(ticket.responses) == 2
    assert {r.user_id for r in ticket.responses} == {test_user["id"], test_user2["id"]}

    session.delete(ticket)
    session.commit()

    remaining_responses = (
        session.query(TicketResponseModel).filter_by(ticket_id=ticket.id).all()
    )
    assert remaining_responses == []
