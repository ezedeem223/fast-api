"""Business account services for verification and transaction handling."""

from __future__ import annotations

from sqlalchemy.orm import Session

from app import schemas
from app.modules.social.models import BusinessTransaction
from app.modules.users.models import User, UserType, VerificationStatus
from app.modules.utils.files import save_upload_file
from fastapi import HTTPException, status


class BusinessService:
    """Encapsulates business registration, verification, and transaction flows."""

    def __init__(self, db: Session):
        self.db = db

    def register_business(
        self, *, current_user: User, business_info: schemas.BusinessRegistration
    ) -> User:
        if current_user.user_type == UserType.BUSINESS:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="User is already registered as a business",
            )

        current_user.user_type = UserType.BUSINESS
        current_user.business_name = business_info.business_name
        current_user.business_registration_number = (
            business_info.business_registration_number
        )
        current_user.bank_account_info = business_info.bank_account_info

        self.db.commit()
        self.db.refresh(current_user)
        return current_user

    async def verify_business(
        self,
        *,
        current_user: User,
        files: schemas.BusinessVerificationUpdate,
        save_upload_fn=save_upload_file,
    ) -> User:
        if current_user.user_type != UserType.BUSINESS:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="User is not registered as a business",
            )

        current_user.id_document_url = await save_upload_fn(files.id_document)
        current_user.passport_url = await save_upload_fn(files.passport)
        current_user.business_document_url = await save_upload_fn(
            files.business_document
        )
        current_user.selfie_url = await save_upload_fn(files.selfie)
        current_user.verification_status = VerificationStatus.PENDING

        self.db.commit()
        self.db.refresh(current_user)
        return current_user

    def create_transaction(
        self,
        *,
        current_user: User,
        payload: schemas.BusinessTransactionCreate,
    ) -> BusinessTransaction:
        if not current_user.is_verified_business:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Business is not verified",
            )

        client_user = (
            self.db.query(User).filter(User.id == payload.client_user_id).first()
        )
        if not client_user:
            raise HTTPException(status_code=404, detail="Client user not found")

        commission = payload.amount * 0.05
        new_transaction = BusinessTransaction(
            business_user_id=current_user.id,
            client_user_id=client_user.id,
            amount=payload.amount,
            commission=commission,
            status="pending",
        )
        self.db.add(new_transaction)
        self.db.commit()
        self.db.refresh(new_transaction)
        return new_transaction

    def list_transactions(self, *, current_user: User) -> list[BusinessTransaction]:
        if not current_user.is_verified_business:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Business is not verified",
            )

        return (
            self.db.query(BusinessTransaction)
            .filter(BusinessTransaction.business_user_id == current_user.id)
            .all()
        )
