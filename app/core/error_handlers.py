"""
Global Exception Handlers for the Application
Provides unified error response format and logging.
"""

import logging
import traceback
from datetime import datetime, timezone
from typing import Union

from fastapi import FastAPI, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from sqlalchemy.exc import SQLAlchemyError
from slowapi.errors import RateLimitExceeded

from app.core.exceptions import AppException

logger = logging.getLogger(__name__)


def create_error_response(
    status_code: int,
    error_code: str,
    message: str,
    details: dict = None,
    path: str = None,
) -> JSONResponse:
    """
    Create a standardized error response.

    Args:
        status_code: HTTP status code
        error_code: Application-specific error code
        message: Human-readable error message
        details: Additional error details
        path: Request path where error occurred

    Returns:
        JSONResponse with standardized error format
    """
    content = {
        "success": False,
        "error": {
            "code": error_code,
            "message": message,
            "details": details or {},
        },
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }

    if path:
        content["path"] = path

    return JSONResponse(
        status_code=status_code,
        content=content,
    )


def register_exception_handlers(app: FastAPI) -> None:
    """
    Register all exception handlers for the application.

    Args:
        app: FastAPI application instance
    """

    @app.exception_handler(AppException)
    async def app_exception_handler(request: Request, exc: AppException):
        """Handle custom application exceptions."""
        logger.error(
            f"AppException: {exc.error_code} - {exc.message}",
            extra={
                "path": request.url.path,
                "method": request.method,
                "error_code": exc.error_code,
                "details": exc.details,
            },
        )

        return create_error_response(
            status_code=exc.status_code,
            error_code=exc.error_code,
            message=exc.message,
            details=exc.details,
            path=request.url.path,
        )

    @app.exception_handler(RequestValidationError)
    async def validation_exception_handler(
        request: Request, exc: RequestValidationError
    ):
        """Handle request validation errors."""
        errors = []
        for error in exc.errors():
            field = ".".join(str(loc) for loc in error["loc"] if loc != "body")
            errors.append(
                {
                    "field": field,
                    "message": error["msg"],
                    "type": error["type"],
                }
            )

        logger.warning(
            f"Validation error on {request.url.path}",
            extra={
                "path": request.url.path,
                "method": request.method,
                "errors": errors,
            },
        )

        content = {
            "success": False,
            "error": {
                "code": "validation_error",
                "message": "Request validation failed",
                "details": {"errors": errors},
            },
            "detail": exc.errors(),
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "path": request.url.path,
        }

        return JSONResponse(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            content=content,
        )

    @app.exception_handler(RateLimitExceeded)
    async def rate_limit_handler(request: Request, exc: RateLimitExceeded):
        """Handle rate limit exceeded errors."""
        logger.warning(
            f"Rate limit exceeded for {request.client.host}",
            extra={
                "path": request.url.path,
                "method": request.method,
                "client_ip": request.client.host,
            },
        )

        return create_error_response(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            error_code="rate_limit_exceeded",
            message="Too many requests. Please try again later.",
            details={"retry_after": str(exc.detail)},
            path=request.url.path,
        )

    @app.exception_handler(SQLAlchemyError)
    async def sqlalchemy_exception_handler(request: Request, exc: SQLAlchemyError):
        """Handle database errors."""
        logger.error(
            f"Database error: {str(exc)}",
            extra={
                "path": request.url.path,
                "method": request.method,
                "error_type": type(exc).__name__,
            },
            exc_info=True,
        )

        return create_error_response(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            error_code="database_error",
            message="A database error occurred. Please try again later.",
            path=request.url.path,
        )

    @app.exception_handler(Exception)
    async def general_exception_handler(request: Request, exc: Exception):
        """Handle all other unhandled exceptions."""
        logger.error(
            f"Unhandled exception: {str(exc)}",
            extra={
                "path": request.url.path,
                "method": request.method,
                "error_type": type(exc).__name__,
                "traceback": traceback.format_exc(),
            },
            exc_info=True,
        )

        # في الـ production، لا نعرض تفاصيل الخطأ الداخلي
        message = "An unexpected error occurred. Please try again later."
        details = {}

        # في الـ development، نعرض التفاصيل
        if hasattr(request.app.state, "environment"):
            env = request.app.state.environment.lower()
            if env in ("development", "dev", "test"):
                message = str(exc)
                details = {
                    "error_type": type(exc).__name__,
                    "traceback": traceback.format_exc().split("\n"),
                }

        return create_error_response(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            error_code="internal_server_error",
            message=message,
            details=details,
            path=request.url.path,
        )
