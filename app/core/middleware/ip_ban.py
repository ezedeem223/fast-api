"""IP ban middleware.

Blocks requests from banned IPs in non-test environments; skips checks in tests to keep fixtures light.
"""

from fastapi import Request
from fastapi.responses import JSONResponse

from app.core.config import settings
from app.core.database import get_db
from app.modules.utils.network import get_client_ip, is_ip_banned


async def ip_ban_middleware(request: Request, call_next):
    """
    Block requests originating from banned IP addresses in non-test environments.
    """
    if settings.environment.lower() == "test":
        return await call_next(request)

    db_gen = get_db()
    db = next(db_gen)
    try:
        client_ip = get_client_ip(request)
        if is_ip_banned(db, client_ip):
            return JSONResponse(
                status_code=403,
                content={"detail": "Your IP address is banned"},
            )
        return await call_next(request)
    finally:
        db_gen.close()
