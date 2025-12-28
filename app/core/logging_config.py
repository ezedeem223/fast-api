"""Logging configuration.

Provides structured, rotating logs with optional JSON output. Binds lightweight contextvars
(request_id/user_id/ip) to every record for correlation across middleware and handlers.
"""

import logging
import logging.handlers
import sys
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional
from contextvars import ContextVar

# Context variables used across middleware/handlers to enrich logs
request_id_ctx: ContextVar[Optional[str]] = ContextVar("request_id", default=None)
user_id_ctx: ContextVar[Optional[int]] = ContextVar("user_id", default=None)
ip_ctx: ContextVar[Optional[str]] = ContextVar("ip_address", default=None)


class JSONFormatter(logging.Formatter):
    """Emit logs as JSON for aggregation (ELK/Splunk/etc.)."""

    def format(self, record: logging.LogRecord) -> str:
        log_data = {
            "timestamp": datetime.fromtimestamp(
                record.created, tz=timezone.utc
            ).isoformat().replace("+00:00", "Z"),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            "module": record.module,
            "function": record.funcName,
            "line": record.lineno,
        }

        # Add extra fields if present
        if hasattr(record, "user_id"):
            log_data["user_id"] = record.user_id
        if hasattr(record, "request_id"):
            log_data["request_id"] = record.request_id
        if hasattr(record, "ip_address"):
            log_data["ip_address"] = record.ip_address
        if hasattr(record, "endpoint"):
            log_data["endpoint"] = record.endpoint
        if hasattr(record, "method"):
            log_data["method"] = record.method
        if hasattr(record, "status_code"):
            log_data["status_code"] = record.status_code
        if hasattr(record, "duration"):
            log_data["duration_ms"] = record.duration

        # Add exception info if present
        if record.exc_info:
            log_data["exception"] = self.formatException(record.exc_info)

        return json.dumps(log_data, ensure_ascii=False)


class ColoredFormatter(logging.Formatter):
    """Add ANSI colors to console output for local readability."""

    # ANSI color codes
    COLORS = {
        "DEBUG": "\033[36m",  # Cyan
        "INFO": "\033[32m",  # Green
        "WARNING": "\033[33m",  # Yellow
        "ERROR": "\033[31m",  # Red
        "CRITICAL": "\033[35m",  # Magenta
    }
    RESET = "\033[0m"

    def format(self, record: logging.LogRecord) -> str:
        # Add color to level name
        levelname = record.levelname
        if levelname in self.COLORS:
            record.levelname = f"{self.COLORS[levelname]}{levelname}{self.RESET}"

        # Format the message
        result = super().format(record)

        # Reset levelname for future use
        record.levelname = levelname

        return result


class ContextEnricher(logging.Filter):
    """Inject contextvars (request_id, user_id, ip_address) into every log record."""

    def filter(self, record: logging.LogRecord) -> bool:  # pragma: no cover - trivial
        request_id = request_id_ctx.get()
        user_id = user_id_ctx.get()
        ip_address = ip_ctx.get()
        if request_id and not hasattr(record, "request_id"):
            record.request_id = request_id
        if user_id and not hasattr(record, "user_id"):
            record.user_id = user_id
        if ip_address and not hasattr(record, "ip_address"):
            record.ip_address = ip_address
        return True


def bind_request_context(
    *, request_id: Optional[str] = None, user_id: Optional[int] = None, ip_address: Optional[str] = None
):
    """Bind request context into contextvars; returns tokens for reset."""
    tokens = []
    if request_id is not None:
        tokens.append(("request_id", request_id_ctx.set(request_id)))
    if user_id is not None:
        tokens.append(("user_id", user_id_ctx.set(user_id)))
    if ip_address is not None:
        tokens.append(("ip_address", ip_ctx.set(ip_address)))
    return tokens


def reset_request_context(tokens):
    """Reset bound contextvars using tokens returned by bind_request_context."""
    for key, token in tokens:
        if key == "request_id":
            request_id_ctx.reset(token)
        elif key == "user_id":
            user_id_ctx.reset(token)
        elif key == "ip_address":
            ip_ctx.reset(token)


def setup_logging(
    log_level: str = "INFO",
    log_dir: Optional[str] = None,
    app_name: str = "fastapi_app",
    max_bytes: int = 10 * 1024 * 1024,  # 10 MB
    backup_count: int = 5,
    use_json: bool = False,
    use_colors: bool = True,
) -> None:
    """Configure root logging.

    Args:
        log_level: Minimum logging level (DEBUG, INFO, WARNING, ERROR, CRITICAL).
        log_dir: Directory to store log files; if None, logs only to console.
        app_name: Application name used in log filenames.
        max_bytes: Max size per log file before rotation.
        backup_count: Number of rotated files to keep.
        use_json: If True, use JSON for file handlers (better for aggregation).
        use_colors: If True, add ANSI colors to console output.
    """
    # Create log directory if specified
    if log_dir:
        log_path = Path(log_dir)
        log_path.mkdir(parents=True, exist_ok=True)

    def _reset_handlers(logger: logging.Logger) -> None:
        """Close and remove any existing handlers to avoid descriptor leaks."""
        for handler in list(logger.handlers):
            try:
                handler.flush()
            finally:
                handler.close()
                logger.removeHandler(handler)

    # Get root logger
    root_logger = logging.getLogger()
    root_logger.setLevel(getattr(logging, log_level.upper()))
    _reset_handlers(root_logger)
    context_filter = ContextEnricher()
    root_logger.addFilter(context_filter)

    # Console Handler
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(getattr(logging, log_level.upper()))

    if use_colors:
        console_format = ColoredFormatter(
            "%(asctime)s | %(levelname)-8s | %(name)s:%(funcName)s:%(lineno)d | %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S",
        )
    else:
        console_format = logging.Formatter(
            "%(asctime)s | %(levelname)-8s | %(name)s:%(funcName)s:%(lineno)d | %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S",
        )

    console_handler.setFormatter(console_format)
    root_logger.addHandler(console_handler)

    # File Handlers (if log_dir is specified)
    if log_dir:
        log_path = Path(log_dir)

        # General log file (all levels)
        general_log = log_path / f"{app_name}.log"
        general_handler = logging.handlers.RotatingFileHandler(
            general_log,
            maxBytes=max_bytes,
            backupCount=backup_count,
            encoding="utf-8",
            delay=True,
        )
        general_handler.setLevel(logging.DEBUG)

        if use_json:
            general_handler.setFormatter(JSONFormatter())
        else:
            general_handler.setFormatter(
                logging.Formatter(
                    "%(asctime)s | %(levelname)-8s | %(name)s:%(funcName)s:%(lineno)d | %(message)s",
                    datefmt="%Y-%m-%d %H:%M:%S",
                )
            )

        root_logger.addHandler(general_handler)

        # Error log file (ERROR and CRITICAL only)
        error_log = log_path / f"{app_name}_error.log"
        error_handler = logging.handlers.RotatingFileHandler(
            error_log,
            maxBytes=max_bytes,
            backupCount=backup_count,
            encoding="utf-8",
            delay=True,
        )
        error_handler.setLevel(logging.ERROR)

        if use_json:
            error_handler.setFormatter(JSONFormatter())
        else:
            error_handler.setFormatter(
                logging.Formatter(
                    "%(asctime)s | %(levelname)-8s | %(name)s:%(funcName)s:%(lineno)d | %(message)s\n"
                    "Exception: %(exc_info)s",
                    datefmt="%Y-%m-%d %H:%M:%S",
                )
            )

        root_logger.addHandler(error_handler)

        # Access log file (for HTTP requests)
        access_log = log_path / f"{app_name}_access.log"
        access_handler = logging.handlers.RotatingFileHandler(
            access_log,
            maxBytes=max_bytes,
            backupCount=backup_count,
            encoding="utf-8",
            delay=True,
        )
        access_handler.setLevel(logging.INFO)

        if use_json:
            access_handler.setFormatter(JSONFormatter())
        else:
            access_handler.setFormatter(
                logging.Formatter(
                    "%(asctime)s | %(method)s %(endpoint)s | Status: %(status_code)s | Duration: %(duration)sms | IP: %(ip_address)s",
                    datefmt="%Y-%m-%d %H:%M:%S",
                )
            )

        # Create dedicated logger for access logs
        access_logger = logging.getLogger("access")
        _reset_handlers(access_logger)
        access_logger.addHandler(access_handler)
        access_logger.setLevel(logging.INFO)
        access_logger.propagate = False
        access_logger.addFilter(context_filter)

    # Suppress noisy loggers
    logging.getLogger("urllib3").setLevel(logging.WARNING)
    logging.getLogger("asyncio").setLevel(logging.WARNING)
    logging.getLogger("multipart").setLevel(logging.WARNING)

    logging.info(
        f"Logging configured. Level: {log_level}, Directory: {log_dir or 'console only'}"
    )


def get_logger(name: str) -> logging.Logger:
    """
    Get a logger instance with the specified name.

    Args:
        name: Logger name (typically __name__ of the module)

    Returns:
        Configured logger instance
    """
    return logging.getLogger(name)


# Convenience function for access logging
def log_request(
    method: str,
    endpoint: str,
    status_code: int,
    duration_ms: float,
    ip_address: str,
    user_id: Optional[int] = None,
    request_id: Optional[str] = None,
) -> None:
    """
    Log an HTTP request with structured data.

    Args:
        method: HTTP method (GET, POST, etc.)
        endpoint: Request endpoint/path
        status_code: HTTP status code
        duration_ms: Request duration in milliseconds
        ip_address: Client IP address
        user_id: User ID if authenticated
        request_id: Unique request ID for tracking
    """
    logger = logging.getLogger("access")
    extra = {
        "method": method,
        "endpoint": endpoint,
        "status_code": status_code,
        "duration": f"{duration_ms:.2f}",
        "ip_address": ip_address,
    }

    if user_id:
        extra["user_id"] = user_id
    if request_id:
        extra["request_id"] = request_id

    message = f"{method} {endpoint} - {status_code} - {duration_ms:.2f}ms"
    logger.info(message, extra=extra)
