"""Impact router for issuing impact certificates and managing cultural dictionary entries."""

from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.oauth2 import get_current_user
from app import models
from app.modules.social.models import ImpactCertificate, CulturalDictionaryEntry

from pydantic import BaseModel, ConfigDict


class ImpactCertificateCreate(BaseModel):
    title: str
    description: Optional[str] = None
    impact_metrics: dict = {}


class ImpactCertificateOut(BaseModel):
    id: int
    user_id: int
    title: str
    description: Optional[str]
    impact_metrics: dict

    model_config = ConfigDict(from_attributes=True)


class CulturalEntryCreate(BaseModel):
    term: str
    definition: str
    cultural_context: str
    language: str = "ar"


class CulturalEntryOut(BaseModel):
    id: int
    term: str
    definition: str
    cultural_context: str
    language: str
    is_verified: bool

    model_config = ConfigDict(from_attributes=True)


router = APIRouter(prefix="/impact", tags=["Impact"])


@router.post("/certificates", response_model=ImpactCertificateOut, status_code=201)
def create_certificate(
    payload: ImpactCertificateCreate,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    cert = ImpactCertificate(
        user_id=current_user.id,
        title=payload.title,
        description=payload.description,
        impact_metrics=payload.impact_metrics or {},
    )
    db.add(cert)
    db.commit()
    db.refresh(cert)
    return cert


@router.get("/certificates", response_model=List[ImpactCertificateOut])
def list_certificates(
    db: Session = Depends(get_db), current_user: models.User = Depends(get_current_user)
):
    certs = (
        db.query(ImpactCertificate)
        .filter(ImpactCertificate.user_id == current_user.id)
        .all()
    )
    return certs


@router.post("/cultural-dictionary", response_model=CulturalEntryOut, status_code=201)
def create_cultural_entry(
    payload: CulturalEntryCreate,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    entry = CulturalDictionaryEntry(
        term=payload.term,
        definition=payload.definition,
        cultural_context=payload.cultural_context,
        language=payload.language,
        submitted_by=current_user.id,
        is_verified=False,
    )
    db.add(entry)
    db.commit()
    db.refresh(entry)
    return entry


@router.get("/cultural-dictionary", response_model=List[CulturalEntryOut])
def list_cultural_entries(
    q: Optional[str] = Query(None, min_length=1),
    db: Session = Depends(get_db),
):
    query = db.query(CulturalDictionaryEntry)
    if q:
        like = f"%{q}%"
        query = query.filter(
            (CulturalDictionaryEntry.term.ilike(like))
            | (CulturalDictionaryEntry.definition.ilike(like))
        )
    return query.all()
