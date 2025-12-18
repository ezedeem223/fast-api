"""Fact checking router for submitting facts, verifications, corrections, and badges."""

from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.oauth2 import get_current_user
from app.modules.fact_checking.models import FactCheckStatus, Fact
from app.modules.fact_checking.service import FactCheckingService
from app.modules.users.models import User

router = APIRouter(prefix="/fact-checking", tags=["Fact Checking"])

# Schemas
from pydantic import BaseModel


class FactSubmitRequest(BaseModel):
    claim: str
    description: Optional[str] = None
    evidence_links: Optional[List[str]] = None
    sources: Optional[List[str]] = None


class FactVerifyRequest(BaseModel):
    verdict: FactCheckStatus
    confidence_score: float
    explanation: Optional[str] = None
    evidence: Optional[List[str]] = None


class FactCorrectionRequest(BaseModel):
    corrected_claim: str
    reason: Optional[str] = None


class FactVoteRequest(BaseModel):
    vote_type: str  # "support" or "oppose"


# Endpoints


@router.post("/submit")
async def submit_fact(
    request: FactSubmitRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """   """
    fact = FactCheckingService.submit_fact(
        db=db,
        claim=request.claim,
        submitter_id=current_user.id,
        description=request.description,
        evidence_links=request.evidence_links,
        sources=request.sources,
    )
    return {
        "id": fact.id,
        "claim": fact.claim,
        "status": fact.status,
        "created_at": fact.created_at,
    }


@router.post("/verify/{fact_id}")
async def verify_fact(
    fact_id: int,
    request: FactVerifyRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """  """
    fact = FactCheckingService.get_fact_by_id(db, fact_id)
    if not fact:
        raise HTTPException(status_code=404, detail="Fact not found")

    verification = FactCheckingService.verify_fact(
        db=db,
        fact_id=fact_id,
        verifier_id=current_user.id,
        verdict=request.verdict,
        confidence_score=request.confidence_score,
        explanation=request.explanation,
        evidence=request.evidence,
    )
    return {
        "id": verification.id,
        "fact_id": verification.fact_id,
        "verdict": verification.verdict,
        "confidence_score": verification.confidence_score,
    }


@router.post("/correct/{fact_id}")
async def correct_fact(
    fact_id: int,
    request: FactCorrectionRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """ """
    fact = FactCheckingService.get_fact_by_id(db, fact_id)
    if not fact:
        raise HTTPException(status_code=404, detail="Fact not found")

    correction = FactCheckingService.correct_fact(
        db=db,
        fact_id=fact_id,
        corrector_id=current_user.id,
        corrected_claim=request.corrected_claim,
        reason=request.reason,
    )
    return {
        "id": correction.id,
        "fact_id": correction.fact_id,
        "corrected_claim": correction.corrected_claim,
    }


@router.post("/vote/{fact_id}")
async def vote_on_fact(
    fact_id: int,
    request: FactVoteRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """  """
    fact = FactCheckingService.get_fact_by_id(db, fact_id)
    if not fact:
        raise HTTPException(status_code=404, detail="Fact not found")

    vote = FactCheckingService.vote_on_fact(
        db=db, fact_id=fact_id, voter_id=current_user.id, vote_type=request.vote_type
    )
    return {"id": vote.id, "fact_id": vote.fact_id, "vote_type": vote.vote_type}


@router.get("/facts/{fact_id}")
async def get_fact(fact_id: int, db: Session = Depends(get_db)):
    """Retrieve a fact by id."""
    fact = FactCheckingService.get_fact_by_id(db, fact_id)
    if not fact:
        raise HTTPException(status_code=404, detail="Fact not found")

    return {
        "id": fact.id,
        "claim": fact.claim,
        "status": fact.status,
        "verification_score": fact.verification_score,
        "community_consensus": fact.community_consensus,
        "support_votes": fact.support_votes,
        "oppose_votes": fact.oppose_votes,
        "verification_count": fact.verification_count,
        "created_at": fact.created_at,
    }


@router.get("/facts")
async def list_facts(
    status: Optional[FactCheckStatus] = None,
    skip: int = Query(0, ge=0),
    limit: int = Query(10, ge=1, le=100),
    db: Session = Depends(get_db),
):
    """   """
    if status:
        facts = FactCheckingService.get_facts_by_status(db, status, skip, limit)
    else:
        facts = db.query(Fact).offset(skip).limit(limit).all()

    return [
        {
            "id": fact.id,
            "claim": fact.claim,
            "status": fact.status,
            "verification_score": fact.verification_score,
        }
        for fact in facts
    ]


@router.get("/search")
async def search_facts(
    q: str = Query(..., min_length=1),
    skip: int = Query(0, ge=0),
    limit: int = Query(10, ge=1, le=100),
    db: Session = Depends(get_db),
):
    """  """
    facts = FactCheckingService.search_facts(db, q, skip, limit)
    return [
        {
            "id": fact.id,
            "claim": fact.claim,
            "status": fact.status,
            "verification_score": fact.verification_score,
        }
        for fact in facts
    ]
