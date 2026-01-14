"""Test module for test session26 fact checking service."""
from app import models
from app.modules.fact_checking import FactCheckStatus
from app.modules.fact_checking.service import FactCheckingService


def _post(session, owner_id=1):
    """Helper for  post."""
    post = models.Post(
        owner_id=owner_id,
        title="t",
        content="c",
        is_safe_content=True,
    )
    session.add(post)
    session.commit()
    session.refresh(post)
    return post


def _comment(session, *, post_id: int, owner_id: int = 1):
    """Helper for  comment."""
    comment = models.Comment(
        owner_id=owner_id,
        post_id=post_id,
        content="c",
        language="en",
    )
    session.add(comment)
    session.commit()
    session.refresh(comment)
    return comment


def test_submit_and_verify_fact(session):
    """Test case for test submit and verify fact."""
    svc = FactCheckingService()
    fact = svc.submit_fact(
        session,
        claim="Earth is round",
        submitter_id=1,
        evidence_links=["link"],
        sources=["src"],
    )
    assert fact.claim == "Earth is round"
    verification = svc.verify_fact(
        session,
        fact_id=fact.id,
        verifier_id=2,
        verdict=FactCheckStatus.VERIFIED,
        confidence_score=0.9,
        explanation="obvious",
        evidence=["img"],
    )
    assert verification.verdict == FactCheckStatus.VERIFIED
    refetched = svc.get_fact_by_id(session, fact.id)
    assert refetched.verification_score >= 0.0
    assert refetched.status in {
        FactCheckStatus.VERIFIED,
        FactCheckStatus.PARTIALLY_TRUE,
        FactCheckStatus.FALSE,
    }


def test_correction_and_override(session):
    """Test case for test correction and override."""
    svc = FactCheckingService()
    fact = svc.submit_fact(session, claim="Old claim", submitter_id=1)
    correction = svc.correct_fact(
        session, fact_id=fact.id, corrector_id=2, corrected_claim="New claim"
    )
    assert correction.corrected_claim == "New claim"

    overridden = svc.override_fact_status(
        session,
        fact_id=fact.id,
        admin_id=99,
        status=FactCheckStatus.FALSE,
        note="bad data",
    )
    assert overridden.status == FactCheckStatus.FALSE
    assert "override" in overridden.description


def test_vote_updates_consensus(session):
    """Test case for test vote updates consensus."""
    svc = FactCheckingService()
    fact = svc.submit_fact(session, claim="Vote claim", submitter_id=1)
    vote1 = svc.vote_on_fact(session, fact_id=fact.id, voter_id=1, vote_type="support")
    vote2 = svc.vote_on_fact(session, fact_id=fact.id, voter_id=2, vote_type="oppose")
    assert vote1.vote_type == "support"
    assert vote2.vote_type == "oppose"
    updated = svc.get_fact_by_id(session, fact.id)
    assert 0 <= updated.community_consensus <= 1


def test_add_misinformation_warning(session):
    """Test case for test add misinformation warning."""
    svc = FactCheckingService()
    post = _post(session)
    warning = svc.add_misinformation_warning(
        session,
        post_id=post.id,
        comment_id=None,
        warning_type="danger",
        related_fact_id=None,
    )
    assert warning.warning_type == "danger"


def test_misinformation_warning_tied_to_fact_and_comment(session):
    """Test case for test misinformation warning tied to fact and comment."""
    svc = FactCheckingService()
    fact = svc.submit_fact(session, claim="False claim", submitter_id=10)
    post = _post(session)
    comment = _comment(session, post_id=post.id)
    warning = svc.add_misinformation_warning(
        session,
        post_id=None,
        comment_id=comment.id,
        warning_type="comment_flag",
        related_fact_id=fact.id,
    )
    assert warning.related_fact_id == fact.id
    assert warning.comment_id == comment.id


def test_multiple_warnings_do_not_duplicate_fact(session):
    """Test case for test multiple warnings do not duplicate fact."""
    svc = FactCheckingService()
    fact = svc.submit_fact(session, claim="Dup claim", submitter_id=11)
    post = _post(session)
    w1 = svc.add_misinformation_warning(
        session,
        post_id=post.id,
        comment_id=None,
        warning_type="warn",
        related_fact_id=fact.id,
    )
    w2 = svc.add_misinformation_warning(
        session,
        post_id=post.id,
        comment_id=None,
        warning_type="warn",
        related_fact_id=fact.id,
    )
    assert w1.related_fact_id == fact.id
    assert w2.related_fact_id == fact.id
    assert (
        session.query(models.MisinformationWarning)
        .filter_by(related_fact_id=fact.id)
        .count()
        == 2
    )
