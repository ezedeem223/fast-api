# app/modules/fact_checking/service.py

from sqlalchemy.orm import Session
from datetime import datetime, timezone
from typing import List, Optional
from app.modules.fact_checking.models import (
    Fact,
    FactVerification,
    FactCorrection,
    CredibilityBadge,
    FactVote,
    MisinformationWarning,
    FactCheckStatus,
)


class FactCheckingService:

    @staticmethod
    def submit_fact(
        db: Session,
        claim: str,
        submitter_id: int,
        description: Optional[str] = None,
        evidence_links: List[str] = None,
        sources: List[str] = None,
    ) -> Fact:
        """Create a fact submission; evidence/sources default to empty lists to keep serialization stable."""
        fact = Fact(
            claim=claim,
            submitter_id=submitter_id,
            description=description,
            evidence_links=evidence_links or [],
            sources=sources or [],
        )
        db.add(fact)
        db.commit()
        db.refresh(fact)
        return fact

    @staticmethod
    def verify_fact(
        db: Session,
        fact_id: int,
        verifier_id: int,
        verdict: FactCheckStatus,
        confidence_score: float,
        explanation: Optional[str] = None,
        evidence: List[str] = None,
    ) -> FactVerification:
        fact = db.query(Fact).filter(Fact.id == fact_id).first()
        if not fact:
            raise ValueError("Fact not found")

        verification = FactVerification(
            fact_id=fact_id,
            verifier_id=verifier_id,
            verdict=verdict,
            confidence_score=confidence_score,
            explanation=explanation,
            evidence_provided=evidence or [],
        )
        db.add(verification)
        db.flush()

        fact.verification_count += 1
        fact.updated_at = datetime.now(timezone.utc)

        FactCheckingService._update_verification_score(db, fact)

        db.commit()
        db.refresh(verification)
        return verification

    @staticmethod
    def correct_fact(
        db: Session,
        fact_id: int,
        corrector_id: int,
        corrected_claim: str,
        reason: Optional[str] = None,
    ) -> FactCorrection:
        fact = db.query(Fact).filter(Fact.id == fact_id).first()
        if not fact:
            raise ValueError("Fact not found")

        correction = FactCorrection(
            fact_id=fact_id,
            corrector_id=corrector_id,
            original_claim=fact.claim,
            corrected_claim=corrected_claim,
            reason=reason,
        )
        db.add(correction)

        fact.claim = corrected_claim
        fact.updated_at = datetime.now(timezone.utc)

        db.commit()
        db.refresh(correction)
        return correction

    @staticmethod
    def issue_credibility_badge(
        db: Session, fact_id: int, badge_type: str, issuer_id: Optional[int] = None
    ) -> CredibilityBadge:
        badge = CredibilityBadge(
            fact_id=fact_id, badge_type=badge_type, issuer_id=issuer_id
        )
        db.add(badge)

        fact = db.query(Fact).filter(Fact.id == fact_id).first()
        if fact:
            fact.status = FactCheckStatus.VERIFIED
            fact.verified_at = datetime.now(timezone.utc)

        db.commit()
        db.refresh(badge)
        return badge

    @staticmethod
    def vote_on_fact(
        db: Session, fact_id: int, voter_id: int, vote_type: str
    ) -> FactVote:
        fact = db.query(Fact).filter(Fact.id == fact_id).first()
        if not fact:
            raise ValueError("Fact not found")

        existing_vote = (
            db.query(FactVote)
            .filter(FactVote.fact_id == fact_id, FactVote.voter_id == voter_id)
            .first()
        )

        if existing_vote:
            db.delete(existing_vote)

        vote = FactVote(fact_id=fact_id, voter_id=voter_id, vote_type=vote_type)
        db.add(vote)

        if vote_type == "support":
            fact.support_votes += 1
        else:
            fact.oppose_votes += 1

        total_votes = fact.support_votes + fact.oppose_votes
        if total_votes > 0:
            fact.community_consensus = fact.support_votes / total_votes

        db.commit()
        db.refresh(vote)
        return vote

    @staticmethod
    def override_fact_status(
        db: Session,
        *,
        fact_id: int,
        admin_id: int,
        status: FactCheckStatus,
        note: Optional[str] = None,
    ) -> Fact:
        """Allow admins to override a fact's status directly."""
        fact = db.query(Fact).filter(Fact.id == fact_id).first()
        if not fact:
            raise ValueError("Fact not found")

        fact.status = status
        fact.updated_at = datetime.now(timezone.utc)
        fact.verification_score = 1.0 if status == FactCheckStatus.VERIFIED else fact.verification_score
        if note:
            # store note in description history for traceability
            existing = fact.description or ""
            fact.description = f"{existing}\n[override:{admin_id}] {note}".strip()

        db.commit()
        db.refresh(fact)
        return fact

    @staticmethod
    def add_misinformation_warning(
        db: Session,
        post_id: Optional[int],
        comment_id: Optional[int],
        warning_type: str,
        related_fact_id: Optional[int] = None,
    ) -> MisinformationWarning:
        warning = MisinformationWarning(
            post_id=post_id,
            comment_id=comment_id,
            warning_type=warning_type,
            related_fact_id=related_fact_id,
        )
        db.add(warning)
        db.commit()
        db.refresh(warning)
        return warning

    @staticmethod
    def _update_verification_score(db: Session, fact: Fact):
        verifications = (
            db.query(FactVerification).filter(FactVerification.fact_id == fact.id).all()
        )

        if not verifications:
            return

        avg_confidence = sum(v.confidence_score for v in verifications) / len(
            verifications
        )

        verified_count = sum(
            1 for v in verifications if v.verdict == FactCheckStatus.VERIFIED
        )
        positive_ratio = verified_count / len(verifications)

        fact.verification_score = avg_confidence * positive_ratio

        if fact.verification_score >= 0.8:
            fact.status = FactCheckStatus.VERIFIED
        elif fact.verification_score >= 0.5:
            fact.status = FactCheckStatus.PARTIALLY_TRUE
        else:
            fact.status = FactCheckStatus.FALSE

    @staticmethod
    def get_fact_by_id(db: Session, fact_id: int) -> Optional[Fact]:
        return db.query(Fact).filter(Fact.id == fact_id).first()

    @staticmethod
    def get_facts_by_status(
        db: Session, status: FactCheckStatus, skip: int = 0, limit: int = 10
    ) -> List[Fact]:
        return (
            db.query(Fact).filter(Fact.status == status).offset(skip).limit(limit).all()
        )

    @staticmethod
    def search_facts(
        db: Session, query: str, skip: int = 0, limit: int = 10
    ) -> List[Fact]:
        return (
            db.query(Fact)
            .filter(Fact.claim.ilike(f"%{query}%"))
            .offset(skip)
            .limit(limit)
            .all()
        )
