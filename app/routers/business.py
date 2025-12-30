"""Business router for business account verification and transactions."""

# =====================================================
# ==================== Imports ========================
# =====================================================
from typing import List

from sqlalchemy.orm import Session

from app.core.database import get_db
from app.modules.users.models import User
from app.services.business import BusinessService
from fastapi import APIRouter, Depends

# Local imports
from .. import oauth2, schemas

# =====================================================
# =============== Global Variables ====================
# =====================================================
router = APIRouter(prefix="/business", tags=["Business"])


def get_business_service(db: Session = Depends(get_db)) -> BusinessService:
    """Endpoint: get_business_service."""
    return BusinessService(db)


# =====================================================
# ==================== Endpoints ======================
# =====================================================


@router.post("/register", response_model=schemas.BusinessUserOut)
async def register_business(
    business_info: schemas.BusinessRegistration,
    current_user: User = Depends(oauth2.get_current_user),
    service: BusinessService = Depends(get_business_service),
):
    """
    Register a new business account.

    Parameters:
      - business_info: BusinessRegistration schema containing business details.
      - current_user: The authenticated user.
      - db: Database session.

    Process:
      - Checks if the user is already registered as a business.
      - Updates the user's type and business-related fields.
      - Commits changes and returns the updated user.

    """
    return service.register_business(
        current_user=current_user, business_info=business_info
    )


@router.post("/verify", response_model=schemas.BusinessUserOut)
async def verify_business(
    files: schemas.BusinessVerificationUpdate,
    current_user: User = Depends(oauth2.get_current_user),
    service: BusinessService = Depends(get_business_service),
):
    """
    Verify a business account by uploading required documents.

    Parameters:
      - files: BusinessVerificationUpdate schema containing files (ID document, passport, business document, selfie).
      - current_user: The authenticated user.
      - db: Database session.

    Process:
      - Checks if the user is registered as a business.
      - Saves the uploaded files using utils.save_upload_file.
      - Updates verification status to PENDING.
      - Commits changes and returns the updated user.

    """
    return await service.verify_business(current_user=current_user, files=files)


@router.post("/transactions", response_model=schemas.BusinessTransactionOut)
async def create_business_transaction(
    transaction: schemas.BusinessTransactionCreate,
    current_user: User = Depends(oauth2.get_current_user),
    service: BusinessService = Depends(get_business_service),
):
    """
    Create a new business transaction.

    Parameters:
      - transaction: BusinessTransactionCreate schema containing transaction details.
      - current_user: The authenticated business user.
      - db: Database session.

    Process:
      - Checks if the business account is verified.
      - Retrieves the client user by ID.
      - Calculates a 5% commission on the transaction amount.
      - Creates a new transaction with status "pending", commits, and returns the transaction.
    """
    return service.create_transaction(current_user=current_user, payload=transaction)


@router.get("/transactions", response_model=List[schemas.BusinessTransactionOut])
async def get_business_transactions(
    current_user: User = Depends(oauth2.get_current_user),
    service: BusinessService = Depends(get_business_service),
):
    """
    Retrieve a list of business transactions for the current business user.

    Process:
      - Checks if the business account is verified.
      - Returns all transactions associated with the business user.

    """
    return service.list_transactions(current_user=current_user)
