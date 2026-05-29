import time
import logging
import hashlib
from collections import defaultdict

from fastapi import Request, HTTPException
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware

from src.database.db import db
from src.config import TIERS

logger = logging.getLogger(__name__)


class APIKeyMiddleware(BaseHTTPMiddleware):
    PUBLIC_PATHS = {
        "/health", "/docs", "/openapi.json",
        "/api/v1/webui", "/api/v1/generate-key",
        "/api/v1/admin",
        "/obs/overlay", "/obs/overlay/widget",
    }

    async def dispatch(self, request: Request, call_next):
        path = request.url.path

        if path in self.PUBLIC_PATHS:
            return await call_next(request)

        if any(path.startswith(p) for p in ("/api/v1/webui", "/api/v1/config", "/api/v1/analytics", "/api/v1/ws", "/obs/", "/static/")):
            return await call_next(request)

        api_key = request.headers.get("X-API-Key") or request.query_params.get("api_key")
        if not api_key:
            return JSONResponse(
                status_code=401,
                content={"error": "Missing X-API-Key header or api_key query param"},
            )

        key_info = await db.validate_api_key(api_key)
        if not key_info:
            return JSONResponse(
                status_code=403,
                content={"error": "Invalid or inactive API key"},
            )

        request.state.api_key = key_info
        request.state.tier = key_info["tier"]
        return await call_next(request)


class RateLimitMiddleware(BaseHTTPMiddleware):
    def __init__(self, app):
        super().__init__(app)
        self.requests: dict[str, list[float]] = defaultdict(list)

    async def dispatch(self, request: Request, call_next):
        path = request.url.path
        if path in APIKeyMiddleware.PUBLIC_PATHS or path.startswith(("/api/v1/webui", "/obs/")):
            return await call_next(request)

        tier_name = getattr(request.state, "tier", "free")
        tier_config = TIERS.get(tier_name, TIERS["free"])
        limit = tier_config.rate_limit_per_min

        client_ip = request.client.host if request.client else "unknown"
        now = time.time()
        window = 60.0

        self.requests[client_ip] = [t for t in self.requests[client_ip] if now - t < window]
        self.requests[client_ip].append(now)

        if len(self.requests[client_ip]) > limit:
            return JSONResponse(
                status_code=429,
                content={
                    "error": "Rate limit exceeded",
                    "limit": limit,
                    "window_seconds": 60,
                    "tier": tier_name,
                    "tier_limits": {
                        k: v.rate_limit_per_min for k, v in TIERS.items()
                    },
                },
            )

        return await call_next(request)


class ErrorLogMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        start = time.time()

        try:
            response = await call_next(request)
            elapsed = time.time() - start

            logger.info(
                f"{request.method} {request.url.path} -> {response.status_code} "
                f"[{elapsed*1000:.0f}ms]"
            )
            response.headers["X-Processing-Time-Ms"] = f"{elapsed*1000:.0f}"
            return response

        except HTTPException:
            raise
        except Exception as e:
            elapsed = time.time() - start
            logger.error(
                f"{request.method} {request.url.path} -> 500 [{elapsed*1000:.0f}ms]: {e}",
                exc_info=True,
            )
            return JSONResponse(
                status_code=500,
                content={
                    "error": "Internal server error",
                    "detail": str(e) if getattr(request.state, "debug", False) else "An unexpected error occurred",
                },
            )


def setup_middleware(app, debug: bool = False):
    app.add_middleware(ErrorLogMiddleware)
    app.add_middleware(RateLimitMiddleware)
    app.add_middleware(APIKeyMiddleware)
    return app
