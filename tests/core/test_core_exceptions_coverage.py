"""Additional coverage for core exception types."""
import pytest
from fastapi import status

from app.core import exceptions as exc


def test_exception_details_and_headers():
    """Ensure exception subclasses populate details and headers."""
    locked = exc.AccountLockedException(retry_after=30)
    assert locked.status_code == status.HTTP_403_FORBIDDEN
    assert locked.detail["details"]["retry_after"] == "30 seconds"

    rate_limit = exc.RateLimitExceededException(retry_after=5)
    assert rate_limit.status_code == status.HTTP_429_TOO_MANY_REQUESTS
    assert rate_limit.headers["Retry-After"] == "5"

    suspended = exc.AccountSuspendedException()
    assert suspended.detail["error_code"] == "account_suspended"

    token_expired = exc.TokenExpiredException()
    assert token_expired.detail["error_code"] == "token_expired"

    invalid_token = exc.InvalidTokenException()
    assert invalid_token.detail["message"] == "Invalid authentication token"


def test_resource_and_validation_exceptions():
    """Cover resource and validation exception branches."""
    not_found = exc.ResourceNotFoundException("Post", identifier=123)
    assert not_found.detail["details"]["identifier"] == "123"

    conflict = exc.ResourceConflictException("Conflict")
    assert conflict.detail["error_code"] == "resource_conflict"

    already = exc.ResourceAlreadyExistsException("User", field="email")
    assert already.detail["details"]["field"] == "email"

    invalid_type = exc.InvalidFileTypeException(allowed_types=["png", "jpg"])
    assert "allowed_types" in invalid_type.detail["details"]

    size_limit = exc.FileSizeLimitException(max_size="10MB")
    assert size_limit.detail["details"]["max_size"] == "10MB"


def test_business_and_external_exceptions():
    """Cover business logic and external service error classes."""
    limit = exc.MaxLimitExceededException("posts", max_limit=5)
    assert limit.detail["details"]["max_limit"] == 5

    balance = exc.InsufficientBalanceException()
    assert balance.detail["error_code"] == "insufficient_balance"

    external = exc.ExternalServiceException("payments")
    assert external.detail["details"]["service"] == "payments"

    db_error = exc.DatabaseException()
    assert db_error.detail["error_code"] == "database_error"


def test_exception_helpers_raise():
    """Validate helper raise_* functions for coverage."""
    with pytest.raises(exc.ResourceAlreadyExistsException):
        exc.raise_already_exists("User", field="email")

    with pytest.raises(exc.PermissionDeniedException):
        exc.raise_permission_denied("Nope")

    with pytest.raises(exc.ValidationException):
        exc.raise_validation_error("bad", field="name")
