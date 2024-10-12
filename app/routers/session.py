from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from .. import models, schemas, oauth2, crypto
from ..database import get_db

router = APIRouter(prefix="/sessions", tags=["Encrypted Sessions"])


@router.post(
    "/", status_code=status.HTTP_201_CREATED, response_model=schemas.EncryptedSessionOut
)
def create_encrypted_session(
    session: schemas.EncryptedSessionCreate,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(oauth2.get_current_user),
):
    other_user = (
        db.query(models.User).filter(models.User.id == session.other_user_id).first()
    )
    if not other_user:
        raise HTTPException(status_code=404, detail="User not found")

    existing_session = (
        db.query(models.EncryptedSession)
        .filter(
            (models.EncryptedSession.user_id == current_user.id)
            & (models.EncryptedSession.other_user_id == other_user.id)
        )
        .first()
    )

    if existing_session:
        raise HTTPException(status_code=400, detail="Session already exists")

    # إنشاء جلسة Signal جديدة
    signal_protocol = crypto.SignalProtocol()
    signal_protocol.initial_key_exchange(other_user.public_key)

    new_session = models.EncryptedSession(
        user_id=current_user.id,
        other_user_id=other_user.id,
        root_key=signal_protocol.root_key,
        chain_key=signal_protocol.chain_key,
        next_header_key=signal_protocol.next_header_key,
        ratchet_key=signal_protocol.dh_pair.private_bytes_raw(),
    )

    db.add(new_session)
    db.commit()
    db.refresh(new_session)

    return schemas.EncryptedSessionOut(
        id=new_session.id,
        user_id=new_session.user_id,
        other_user_id=new_session.other_user_id,
        created_at=new_session.created_at,
    )


@router.put("/{session_id}", response_model=schemas.EncryptedSessionOut)
def update_encrypted_session(
    session_id: int,
    session_update: schemas.EncryptedSessionUpdate,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(oauth2.get_current_user),
):
    session = (
        db.query(models.EncryptedSession)
        .filter(
            (models.EncryptedSession.id == session_id)
            & (models.EncryptedSession.user_id == current_user.id)
        )
        .first()
    )

    if not session:
        raise HTTPException(status_code=404, detail="Session not found")

    session.root_key = session_update.root_key
    session.chain_key = session_update.chain_key
    session.next_header_key = session_update.next_header_key
    session.ratchet_key = session_update.ratchet_key

    db.commit()
    db.refresh(session)

    return schemas.EncryptedSessionOut(
        id=session.id,
        user_id=session.user_id,
        other_user_id=session.other_user_id,
        created_at=session.created_at,
    )
