from fastapi import APIRouter, Depends, HTTPException, status, UploadFile, File
from sqlalchemy.orm import Session
from .. import models, schemas, oauth2, utils
from ..database import get_db
from typing import List
import os

router = APIRouter(prefix="/business", tags=["Business"])


@router.post("/register", response_model=schemas.BusinessUserOut)
async def register_business(
    business_info: schemas.BusinessRegistration,
    current_user: models.User = Depends(oauth2.get_current_user),
    db: Session = Depends(get_db),
):
    """
    تسجيل حساب تجاري جديد
    """
    if current_user.user_type == models.UserType.BUSINESS:
        raise HTTPException(
            status_code=400, detail="User is already registered as a business"
        )

    current_user.user_type = models.UserType.BUSINESS
    current_user.business_name = business_info.business_name
    current_user.business_registration_number = (
        business_info.business_registration_number
    )
    current_user.bank_account_info = business_info.bank_account_info

    db.commit()
    db.refresh(current_user)
    return current_user


@router.post("/verify", response_model=schemas.BusinessUserOut)
async def verify_business(
    files: schemas.BusinessVerificationUpdate,
    current_user: models.User = Depends(oauth2.get_current_user),
    db: Session = Depends(get_db),
):
    """
    التحقق من الحساب التجاري عن طريق رفع المستندات المطلوبة
    """
    if current_user.user_type != models.UserType.BUSINESS:
        raise HTTPException(
            status_code=400, detail="User is not registered as a business"
        )

    # حفظ الملفات المرفوعة
    current_user.id_document_url = await utils.save_upload_file(files.id_document)
    current_user.passport_url = await utils.save_upload_file(files.passport)
    current_user.business_document_url = await utils.save_upload_file(
        files.business_document
    )
    current_user.selfie_url = await utils.save_upload_file(files.selfie)

    current_user.verification_status = models.VerificationStatus.PENDING

    db.commit()
    db.refresh(current_user)
    return current_user


@router.post("/transactions", response_model=schemas.BusinessTransactionOut)
async def create_business_transaction(
    transaction: schemas.BusinessTransactionCreate,
    current_user: models.User = Depends(oauth2.get_current_user),
    db: Session = Depends(get_db),
):
    """
    إنشاء معاملة تجارية جديدة
    """
    if not current_user.is_verified_business:
        raise HTTPException(status_code=400, detail="Business is not verified")

    client_user = (
        db.query(models.User)
        .filter(models.User.id == transaction.client_user_id)
        .first()
    )
    if not client_user:
        raise HTTPException(status_code=404, detail="Client user not found")

    commission = transaction.amount * 0.05  # عمولة 5%
    new_transaction = models.BusinessTransaction(
        business_user_id=current_user.id,
        client_user_id=client_user.id,
        amount=transaction.amount,
        commission=commission,
        status="pending",
    )

    db.add(new_transaction)
    db.commit()
    db.refresh(new_transaction)
    return new_transaction


@router.get("/transactions", response_model=List[schemas.BusinessTransactionOut])
async def get_business_transactions(
    current_user: models.User = Depends(oauth2.get_current_user),
    db: Session = Depends(get_db),
):
    """
    الحصول على قائمة المعاملات التجارية للمستخدم
    """
    if not current_user.is_verified_business:
        raise HTTPException(status_code=400, detail="Business is not verified")

    transactions = (
        db.query(models.BusinessTransaction)
        .filter(models.BusinessTransaction.business_user_id == current_user.id)
        .all()
    )
    return transactions
