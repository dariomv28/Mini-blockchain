"""Tiered in-memory IP rate limiter middleware enforcing general, mutation, and admin quotas."""

from __future__ import annotations

import math
import time
from collections import defaultdict, deque
from starlette.responses import JSONResponse
from starlette.types import ASGIApp, Receive, Scope, Send


class InMemoryRateLimiterMiddleware:
    def __init__(
        self,
        app: ASGIApp,
        general_limit: int = 120,
        mutation_limit: int = 30,
        admin_limit: int = 5,
        window_seconds: float = 60.0,
    ):
        self.app = app
        self.general_limit = general_limit
        self.mutation_limit = mutation_limit
        self.admin_limit = admin_limit
        self.window = window_seconds

        # IP -> deque of timestamps for each tier
        self._general_history: dict[str, deque[float]] = defaultdict(deque)
        self._mutation_history: dict[str, deque[float]] = defaultdict(deque)
        self._admin_history: dict[str, deque[float]] = defaultdict(deque)
        self._last_cleanup = time.monotonic()

    def _get_client_ip(self, scope: Scope) -> str:
        client = scope.get("client")
        if client and client[0]:
            return str(client[0])
        return "127.0.0.1"

    def _cleanup_old_entries(self, now: float) -> None:
        if now - self._last_cleanup < 30.0:
            return
        self._last_cleanup = now
        cutoff = now - self.window
        for history in (self._general_history, self._mutation_history, self._admin_history):
            empty_keys = []
            for ip, queue in history.items():
                while queue and queue[0] < cutoff:
                    queue.popleft()
                if not queue:
                    empty_keys.append(ip)
            for k in empty_keys:
                history.pop(k, None)

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        # Strictly apply to HTTP requests only, based on ASGI scope type
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        now = time.monotonic()
        cutoff = now - self.window
        ip = self._get_client_ip(scope)
        method = scope.get("method", "GET").upper()
        path = scope.get("path", "")

        is_mutation = method in {"POST", "PUT", "DELETE", "PATCH"}
        is_admin = path.startswith("/api/v1/admin")

        # Clean current queues for this IP
        for q in (self._general_history[ip], self._mutation_history[ip], self._admin_history[ip]):
            while q and q[0] < cutoff:
                q.popleft()

        # Check quotas
        blocked = False
        oldest_ts = now

        # 1. General quota
        if len(self._general_history[ip]) >= self.general_limit:
            blocked = True
            if self._general_history[ip]:
                oldest_ts = min(oldest_ts, self._general_history[ip][0])

        # 2. Mutation quota (mutation consumes general + mutation)
        if not blocked and is_mutation:
            if len(self._mutation_history[ip]) >= self.mutation_limit:
                blocked = True
                if self._mutation_history[ip]:
                    oldest_ts = min(oldest_ts, self._mutation_history[ip][0])

        # 3. Admin quota (admin consumes general + mutation (if POST) + admin)
        if not blocked and is_admin:
            if len(self._admin_history[ip]) >= self.admin_limit:
                blocked = True
                if self._admin_history[ip]:
                    oldest_ts = min(oldest_ts, self._admin_history[ip][0])

        if blocked:
            retry_after = max(1, math.ceil(oldest_ts + self.window - now))
            res = JSONResponse(
                status_code=429,
                headers={"Retry-After": str(retry_after)},
                content={
                    "error": {
                        "code": "RATE_LIMITED",
                        "message": "Too many requests; rate limit exceeded",
                    }
                },
            )
            await res(scope, receive, send)
            return

        # Record usage in all applicable tiers
        self._general_history[ip].append(now)
        if is_mutation:
            self._mutation_history[ip].append(now)
        if is_admin:
            self._admin_history[ip].append(now)

        self._cleanup_old_entries(now)
        await self.app(scope, receive, send)
