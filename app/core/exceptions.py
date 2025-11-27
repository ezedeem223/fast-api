"""
Custom Exception Classes for the Application
Provides a unified error handling system with proper HTTP status codes and messages.
"""

from typing import Any, Dict, Optional
from fastapi import HTTPException, status


class AppException(HTTPException):
    """
    Base exception class for all application exceptions.
    Provides consistent error response format.
    """

    def __init__(
        self,
        status_code: int,
        error_code: str,
        message: str,
        details: Optional[Dict[str, Any]] = None,
        headers: Optional[Dict[str, str]] = None,
    ):
        self.error_code = error_code
        self.message = message
        self.details = details or {}
        super().__init__(
            status_code=status_code,
            detail={
                "error_code": error_code,
                "message": message,
                "details": self.details,
            },
            headers=headers,
        )


# ==================== Authentication Exceptions ====================


class AuthenticationException(AppException):
    """Base class for authentication-related exceptions."""

    def __init__(
        self,
        error_code: str = "authentication_failed",
        message: str = "Authentication failed",
        details: Optional[Dict[str, Any]] = None,
    ):
        super().__init__(
            status_code=status.HTTP_401_UNAUTHORIZED,
            error_code=error_code,
            message=message,
            details=details,
            headers={"WWW-Authenticate": "Bearer"},
        )


class InvalidCredentialsException(AuthenticationException):
    """Raised when user provides invalid credentials."""

    def __init__(self):
        super().__init__(
            error_code="invalid_credentials",
            message="Invalid email or password",
        )


class TokenExpiredException(AuthenticationException):
    """Raised when authentication token has expired."""

    def __init__(self):
        super().__init__(
            error_code="token_expired",
            message="Authentication token has expired",
        )


class InvalidTokenException(AuthenticationException):
    """Raised when authentication token is invalid."""

    def __init__(self):
        super().__init__(
            error_code="invalid_token",
            message="Invalid authentication token",
        )


class AccountSuspendedException(AppException):
    """Raised when user account is suspended."""

    def __init__(self):
        super().__init__(
            status_code=status.HTTP_403_FORBIDDEN,
            error_code="account_suspended",
            message="Your account has been suspended",
        )


class AccountLockedException(AppException):
    """Raised when user account is temporarily locked."""

    def __init__(self, retry_after: Optional[int] = None):
        details = {}
        if retry_after:
            details["retry_after"] = f"{retry_after} seconds"

        super().__init__(
            status_code=status.HTTP_403_FORBIDDEN,
            error_code="account_locked",
            message="Account is temporarily locked. Please try again later.",
            details=details,
        )


class EmailNotVerifiedException(AppException):
    """Raised when user email is not verified."""

    def __init__(self):
        super().__init__(
            status_code=status.HTTP_403_FORBIDDEN,
            error_code="email_not_verified",
            message="Please verify your email address to continue",
        )


# ==================== Authorization Exceptions ====================


class PermissionDeniedException(AppException):
    """Raised when user doesn't have permission to perform an action."""

    def __init__(
        self, message: str = "You don't have permission to perform this action"
    ):
        super().__init__(
            status_code=status.HTTP_403_FORBIDDEN,
            error_code="permission_denied",
            message=message,
        )


class OwnershipRequiredException(PermissionDeniedException):
    """Raised when action requires resource ownership."""

    def __init__(self, resource: str):
        super().__init__(
            message=f"You must be the owner of this {resource} to perform this action"
        )


# ==================== Resource Exceptions ====================


class ResourceNotFoundException(AppException):
    """Raised when a requested resource is not found."""

    def __init__(self, resource: str, identifier: Optional[Any] = None):
        details = {}
        if identifier is not None:
            details["identifier"] = str(identifier)

        super().__init__(
            status_code=status.HTTP_404_NOT_FOUND,
            error_code="resource_not_found",
            message=f"{resource} not found",
            details=details,
        )


class ResourceAlreadyExistsException(AppException):
    """Raised when trying to create a resource that already exists."""

    def __init__(self, resource: str, field: Optional[str] = None):
        details = {}
        if field:
            details["field"] = field

        super().__init__(
            status_code=status.HTTP_409_CONFLICT,
            error_code="resource_already_exists",
            message=f"{resource} already exists",
            details=details,
        )


class ResourceConflictException(AppException):
    """Raised when there's a conflict with the resource state."""

    def __init__(self, message: str, details: Optional[Dict[str, Any]] = None):
        super().__init__(
            status_code=status.HTTP_409_CONFLICT,
            error_code="resource_conflict",
            message=message,
            details=details,
        )


# ==================== Validation Exceptions ====================


class ValidationException(AppException):
    """Raised when input validation fails."""

    def __init__(self, message: str, field: Optional[str] = None):
        details = {}
        if field:
            details["field"] = field

        super().__init__(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            error_code="validation_error",
            message=message,
            details=details,
        )


class InvalidFileTypeException(ValidationException):
    """Raised when uploaded file type is not allowed."""

    def __init__(self, allowed_types: Optional[list] = None):
        details = {}
        if allowed_types:
            details["allowed_types"] = allowed_types

        super().__init__(
            message="Invalid file type",
        )
        self.details.update(details)


class FileSizeLimitException(ValidationException):
    """Raised when uploaded file exceeds size limit."""

    def __init__(self, max_size: Optional[str] = None):
        details = {}
        if max_size:
            details["max_size"] = max_size

        super().__init__(
            message="File size exceeds the limit",
        )
        self.details.update(details)


# ==================== Rate Limiting Exceptions ====================


class RateLimitExceededException(AppException):
    """Raised when rate limit is exceeded."""

    def __init__(self, retry_after: Optional[int] = None):
        details = {}
        if retry_after:
            details["retry_after"] = f"{retry_after} seconds"

        super().__init__(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            error_code="rate_limit_exceeded",
            message="Too many requests. Please try again later.",
            details=details,
            headers={"Retry-After": str(retry_after)} if retry_after else None,
        )


# ==================== Business Logic Exceptions ====================


class BusinessLogicException(AppException):
    """Base class for business logic exceptions."""

    def __init__(
        self,
        error_code: str,
        message: str,
        details: Optional[Dict[str, Any]] = None,
        status_code: int = status.HTTP_400_BAD_REQUEST,
    ):
        super().__init__(
            status_code=status_code,
            error_code=error_code,
            message=message,
            details=details,
        )


class MaxLimitExceededException(BusinessLogicException):
    """Raised when a maximum limit is exceeded."""

    def __init__(self, resource: str, max_limit: int):
        super().__init__(
            error_code="max_limit_exceeded",
            message=f"Maximum number of {resource} exceeded",
            details={"max_limit": max_limit},
        )


class InsufficientBalanceException(BusinessLogicException):
    """Raised when user has insufficient balance."""

    def __init__(self):
        super().__init__(
            error_code="insufficient_balance",
            message="Insufficient balance to complete this operation",
        )


# ==================== External Service Exceptions ====================


class ExternalServiceException(AppException):
    """Raised when an external service fails."""

    def __init__(self, service_name: str, message: Optional[str] = None):
        super().__init__(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            error_code="external_service_error",
            message=message or f"{service_name} service is currently unavailable",
            details={"service": service_name},
        )


class DatabaseException(AppException):
    """Raised when database operation fails."""

    def __init__(self, message: str = "Database operation failed"):
        super().__init__(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            error_code="database_error",
            message=message,
        )


# ==================== Helper Functions ====================


def raise_not_found(resource: str, identifier: Optional[Any] = None):
    """Helper function to raise ResourceNotFoundException."""
    raise ResourceNotFoundException(resource, identifier)


def raise_already_exists(resource: str, field: Optional[str] = None):
    """Helper function to raise ResourceAlreadyExistsException."""
    raise ResourceAlreadyExistsException(resource, field)


def raise_permission_denied(message: Optional[str] = None):
    """Helper function to raise PermissionDeniedException."""
    raise PermissionDeniedException(
        message or "You don't have permission to perform this action"
    )


def raise_validation_error(message: str, field: Optional[str] = None):
    """Helper function to raise ValidationException."""
    raise ValidationException(message, field)
