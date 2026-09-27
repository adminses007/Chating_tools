"""Simple in-memory rate limiting middleware."""
from __future__ import annotations

import time
from collections import defaultdict, deque

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse, Response

from server.config import get_config


class RateLimitMiddleware(BaseHTTPMiddleware):
    def __init__(self, app):
        super().__init__(app)
        self._hits: dict[str, deque[float]] = defaultdict(deque)

    async def dispatch(self, request: Request, call_next) -> Response:
        # Skip rate limit for health and websocket upgrade path handled elsewhere
        if request.url.path in ("/health", "/admin", "/") or request.url.path.startswith(
            ("/admin/", "/css/", "/js/", "/app", "/api/files/")
        ):
            return await call_next(request)
        if request.headers.get("upgrade", "").lower() == "websocket":
            return await call_next(request)

        cfg = get_config()
        limit = int(cfg.get("rate_limit_per_minute", 120))
        ip = request.client.host if request.client else "unknown"
        now = time.time()
        window = 60.0
        q = self._hits[ip]
        while q and now - q[0] > window:
            q.popleft()
        if len(q) >= limit:
            return JSONResponse({"detail": "Rate limit exceeded"}, status_code=429)
        q.append(now)
        return await call_next(request)
