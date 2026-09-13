"""ASGI middleware buffering and verifying actual received HTTP body size."""

from __future__ import annotations

from starlette.responses import JSONResponse
from starlette.types import ASGIApp, Receive, Scope, Send


class RequestSizeLimitMiddleware:
    def __init__(self, app: ASGIApp, max_bytes: int = 1_048_576):
        self.app = app
        self.max_bytes = max_bytes

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        # 1. Fast check Content-Length header if present
        headers = dict(scope.get("headers", []))
        cl_raw = headers.get(b"content-length")
        if cl_raw is not None:
            try:
                cl_str = cl_raw.decode("ascii")
                cl_val = int(cl_str)
                if cl_val < 0:
                    raise ValueError
            except Exception:
                res = JSONResponse(
                    status_code=400,
                    content={
                        "error": {
                            "code": "INVALID_CONTENT_LENGTH",
                            "message": "Content-Length header must be a non-negative integer",
                        }
                    },
                )
                await res(scope, receive, send)
                return

            if cl_val > self.max_bytes:
                res = JSONResponse(
                    status_code=413,
                    content={
                        "error": {
                            "code": "REQUEST_TOO_LARGE",
                            "message": f"Request body exceeds maximum size of {self.max_bytes} bytes",
                        }
                    },
                )
                await res(scope, receive, send)
                return

        method = scope.get("method", "GET").upper()
        # Non-body requests can proceed directly
        if method in {"GET", "HEAD", "OPTIONS"}:
            await self.app(scope, receive, send)
            return

        # 2. Buffer streamed chunks and verify actual bytes received
        received_bytes = 0
        chunks: list[bytes] = []

        while True:
            message = await receive()
            msg_type = message.get("type")
            if msg_type == "http.disconnect":
                return
            if msg_type == "http.request":
                body = message.get("body", b"")
                received_bytes += len(body)
                if received_bytes > self.max_bytes:
                    res = JSONResponse(
                        status_code=413,
                        content={
                            "error": {
                                "code": "REQUEST_TOO_LARGE",
                                "message": f"Request body exceeds maximum size of {self.max_bytes} bytes",
                            }
                        },
                    )
                    await res(scope, receive, send)
                    return

                chunks.append(body)
                if not message.get("more_body", False):
                    break

        full_body = b"".join(chunks)
        delivered = False

        async def buffered_receive() -> dict:
            nonlocal delivered
            if not delivered:
                delivered = True
                return {
                    "type": "http.request",
                    "body": full_body,
                    "more_body": False,
                }
            return await receive()

        await self.app(scope, buffered_receive, send)
