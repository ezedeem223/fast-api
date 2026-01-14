"""Additional coverage for business router endpoints."""

from io import BytesIO
from types import SimpleNamespace

import pytest
from fastapi import BackgroundTasks, UploadFile

from app import schemas
from app.routers import business as business_router


class DummyService:
    """Stub business service capturing inputs."""

    def __init__(self):
        self.seen = {}

    def register_business(self, current_user, business_info):
        self.seen["register"] = (current_user, business_info)
        return {"result": "registered"}

    async def verify_business(self, current_user, files):
        self.seen["verify"] = (current_user, files)
        return {"result": "verified"}

    def create_transaction(self, current_user, payload):
        self.seen["transaction"] = (current_user, payload)
        return {"result": "transaction"}

    def list_transactions(self, current_user):
        self.seen["list_transactions"] = current_user
        return [{"result": "tx"}]

    def list_business_verifications(self, status_filter):
        self.seen["list_verifications"] = status_filter
        return [{"result": "verification"}]

    def review_business_verification(self, user_id, decision):
        self.seen["review"] = (user_id, decision)
        return SimpleNamespace(
            email="biz@example.com",
            is_verified_business=decision.status
            == schemas.VerificationStatus.APPROVED,
        )


@pytest.mark.asyncio
async def test_business_router_register_verify_and_transactions():
    """Cover register/verify/transaction router paths with a stub service."""
    service = DummyService()
    current_user = SimpleNamespace(id=1, email="user@example.com")

    business_info = schemas.BusinessRegistration(
        business_name="Biz",
        business_registration_number="123",
        bank_account_info="bank",
    )
    registered = await business_router.register_business(
        business_info=business_info,
        current_user=current_user,
        service=service,
    )
    assert registered["result"] == "registered"
    assert service.seen["register"][0] is current_user

    id_document = UploadFile(filename="id.txt", file=BytesIO(b"id"))
    passport = UploadFile(filename="pass.txt", file=BytesIO(b"pass"))
    business_document = UploadFile(filename="biz.txt", file=BytesIO(b"biz"))
    selfie = UploadFile(filename="selfie.txt", file=BytesIO(b"selfie"))
    verified = await business_router.verify_business(
        id_document=id_document,
        passport=passport,
        business_document=business_document,
        selfie=selfie,
        current_user=current_user,
        service=service,
    )
    assert verified["result"] == "verified"
    files = service.seen["verify"][1]
    assert files.id_document.filename == "id.txt"
    assert files.passport.filename == "pass.txt"

    transaction = schemas.BusinessTransactionCreate(
        client_user_id=2,
        amount=99.5,
    )
    created = await business_router.create_business_transaction(
        transaction=transaction,
        current_user=current_user,
        service=service,
    )
    assert created["result"] == "transaction"
    listed = await business_router.get_business_transactions(
        current_user=current_user,
        service=service,
    )
    assert listed == [{"result": "tx"}]


@pytest.mark.asyncio
async def test_business_router_verifications_and_review(monkeypatch):
    """Cover listing and reviewing business verifications."""
    service = DummyService()
    admin_user = SimpleNamespace(id=99, email="admin@example.com", is_admin=True)
    status_filter = schemas.VerificationStatus.APPROVED

    listed = await business_router.list_business_verifications(
        status_filter=status_filter,
        current_user=admin_user,
        service=service,
    )
    assert listed == [{"result": "verification"}]
    assert service.seen["list_verifications"] == status_filter

    sent = {}

    def fake_queue(background_tasks, to, subject, body):
        sent["to"] = to
        sent["subject"] = subject
        sent["body"] = body

    monkeypatch.setattr(
        business_router, "queue_email_notification", fake_queue
    )
    decision = schemas.BusinessVerificationDecision(
        status=schemas.VerificationStatus.APPROVED,
        note="extra",
    )
    updated = await business_router.review_business_verification(
        user_id=10,
        decision=decision,
        background_tasks=BackgroundTasks(),
        current_user=admin_user,
        service=service,
    )
    assert updated.email == "biz@example.com"
    assert "approved" in sent["subject"]
    assert "extra" in sent["body"]
