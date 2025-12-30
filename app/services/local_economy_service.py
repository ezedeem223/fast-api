"""Lightweight service helpers for local economy flows (marketplace/learning)."""

from __future__ import annotations

from types import SimpleNamespace

from sqlalchemy.orm import Session

from app import models
from fastapi import HTTPException, status

ALLOWED_CATEGORIES = {"goods", "services", "skills"}


def _ensure_user(user):
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Auth required"
        )
    return user


class LocalEconomyService:
    """Minimal validation/permission wrapper around local economy models."""

    def __init__(self, db: Session):
        self.db = db

    def create_listing(
        self, *, current_user, payload: SimpleNamespace | object
    ) -> models.LocalMarketListing:
        _ensure_user(current_user)
        if not getattr(current_user, "is_verified", False):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN, detail="User not verified"
            )

        title = getattr(payload, "title", "") or ""
        price = getattr(payload, "price", 0)
        category = getattr(payload, "category", None)

        if not title.strip() or price <= 0 or category not in ALLOWED_CATEGORIES:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid listing data"
            )

        listing = models.LocalMarketListing(
            seller_id=current_user.id,
            title=title,
            description=getattr(payload, "description", "") or "",
            category=category,
            latitude=getattr(payload, "latitude", 0.0),
            longitude=getattr(payload, "longitude", 0.0),
            price=price,
            currency=getattr(payload, "currency", "USD"),
        )
        self.db.add(listing)
        self.db.commit()
        self.db.refresh(listing)
        return listing

    def create_inquiry(
        self, *, listing_id: int, current_user, message: str
    ) -> models.LocalMarketInquiry:
        _ensure_user(current_user)
        listing = (
            self.db.query(models.LocalMarketListing)
            .filter(models.LocalMarketListing.id == listing_id)
            .first()
        )
        if not listing:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail="Listing not found"
            )
        if listing.seller_id == current_user.id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Cannot inquire on own listing",
            )
        if not message or not message.strip():
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST, detail="Message is required"
            )

        inquiry = models.LocalMarketInquiry(
            listing_id=listing_id, buyer_id=current_user.id, message=message.strip()
        )
        self.db.add(inquiry)
        listing.inquiries_count += 1
        self.db.commit()
        self.db.refresh(inquiry)
        return inquiry

    def create_transaction(
        self, *, listing_id: int, current_user, quantity: int = 1
    ) -> models.LocalMarketTransaction:
        _ensure_user(current_user)
        listing = (
            self.db.query(models.LocalMarketListing)
            .filter(models.LocalMarketListing.id == listing_id)
            .first()
        )
        if not listing:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail="Listing not found"
            )
        if listing.seller_id == current_user.id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN, detail="Cannot buy own listing"
            )
        if quantity <= 0:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Quantity must be positive",
            )

        amount = (listing.price or 0) * quantity
        txn = models.LocalMarketTransaction(
            listing_id=listing_id,
            buyer_id=current_user.id,
            seller_id=listing.seller_id,
            amount=amount,
            quantity=quantity,
        )
        self.db.add(txn)
        self.db.commit()
        self.db.refresh(txn)
        return txn

    def update_listing(
        self, *, listing_id: int, current_user, payload: SimpleNamespace | object
    ) -> models.LocalMarketListing:
        _ensure_user(current_user)
        listing = (
            self.db.query(models.LocalMarketListing)
            .filter(models.LocalMarketListing.id == listing_id)
            .first()
        )
        if not listing:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail="Listing not found"
            )
        if listing.seller_id != current_user.id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Not authorized to update listing",
            )

        title = getattr(payload, "title", listing.title)
        price = getattr(payload, "price", listing.price)
        description = getattr(payload, "description", listing.description)
        if not title or price is None or price <= 0:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid update data"
            )

        listing.title = title
        listing.price = price
        listing.description = description
        self.db.commit()
        self.db.refresh(listing)
        return listing

    def delete_listing(self, *, listing_id: int, current_user) -> dict:
        _ensure_user(current_user)
        listing = (
            self.db.query(models.LocalMarketListing)
            .filter(models.LocalMarketListing.id == listing_id)
            .first()
        )
        if not listing:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail="Listing not found"
            )
        if listing.seller_id != current_user.id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Not authorized to delete listing",
            )
        self.db.delete(listing)
        self.db.commit()
        return {"message": "Listing deleted"}

    def create_cooperative_transaction(
        self,
        *,
        cooperative_id: int,
        user_id: int,
        amount: float,
        notes: str | None = None,
    ) -> models.CooperativeTransaction:
        if amount <= 0:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Amount must be positive",
            )
        coop = (
            self.db.query(models.DigitalCooperative)
            .filter(models.DigitalCooperative.id == cooperative_id)
            .first()
        )
        if not coop:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail="Cooperative not found"
            )

        member = (
            self.db.query(models.CooperativeMember)
            .filter(
                models.CooperativeMember.cooperative_id == cooperative_id,
                models.CooperativeMember.user_id == user_id,
            )
            .first()
        )
        if not member:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN, detail="Not a cooperative member"
            )

        txn = models.CooperativeTransaction(
            cooperative_id=cooperative_id,
            amount=amount,
            description=notes or "",
        )
        coop.revenue = (coop.revenue or 0) + amount
        self.db.add(txn)
        self.db.commit()
        self.db.refresh(txn)
        return txn


__all__ = ["LocalEconomyService", "ALLOWED_CATEGORIES"]
