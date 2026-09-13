"""Error definitions and exception handling for PyChain API."""

from __future__ import annotations

import logging
from fastapi import FastAPI, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from network.errors import NodeBusyError, NodeClosedError
from storage.errors import StorageError

logger = logging.getLogger("pychain.api.errors")


class APIError(Exception):
    def __init__(self, status_code: int, code: str, message: str):
        super().__init__(message)
        self.status_code = status_code
        self.code = code
        self.message = message


def create_error_response(status_code: int, code: str, message: str) -> JSONResponse:
    return JSONResponse(
        status_code=status_code,
        content={
            "error": {
                "code": code,
                "message": message,
            }
        },
    )


def register_exception_handlers(app: FastAPI) -> None:
    @app.exception_handler(APIError)
    async def api_error_handler(request: Request, exc: APIError) -> JSONResponse:
        return create_error_response(exc.status_code, exc.code, exc.message)



    @app.exception_handler(RequestValidationError)
    async def validation_error_handler(request: Request, exc: RequestValidationError) -> JSONResponse:
        # Format human-readable first error
        errors = exc.errors()
        message = "Invalid request parameter"
        if errors:
            first = errors[0]
            loc = " -> ".join(str(l) for l in first.get("loc", []))
            msg = first.get("msg", "invalid")
            message = f"Validation failed at '{loc}': {msg}"
        return create_error_response(status.HTTP_400_BAD_REQUEST, "VALIDATION_ERROR", message)

    @app.exception_handler(StarletteHTTPException)
    async def http_exception_handler(request: Request, exc: StarletteHTTPException) -> JSONResponse:
        code = "HTTP_ERROR"
        if exc.status_code == status.HTTP_404_NOT_FOUND:
            code = "NOT_FOUND"
        elif exc.status_code == status.HTTP_405_METHOD_NOT_ALLOWED:
            code = "METHOD_NOT_ALLOWED"
        elif exc.status_code == status.HTTP_413_REQUEST_ENTITY_TOO_LARGE:
            code = "REQUEST_TOO_LARGE"
        elif exc.status_code == status.HTTP_429_TOO_MANY_REQUESTS:
            code = "RATE_LIMITED"
        message = exc.detail if isinstance(exc.detail, str) else str(exc.detail)
        return create_error_response(exc.status_code, code, message)

    @app.exception_handler(NodeBusyError)
    async def node_busy_handler(request: Request, exc: NodeBusyError) -> JSONResponse:
        logger.warning("Node busy: %s", exc)
        return create_error_response(status.HTTP_503_SERVICE_UNAVAILABLE, "NODE_BUSY", "Node is currently busy; retry shortly")

    @app.exception_handler(NodeClosedError)
    async def node_closed_handler(request: Request, exc: NodeClosedError) -> JSONResponse:
        logger.error("Node closed: %s", exc)
        return create_error_response(status.HTTP_503_SERVICE_UNAVAILABLE, "NODE_CLOSED", "Blockchain node is not running")

    @app.exception_handler(StorageError)
    async def storage_error_handler(request: Request, exc: StorageError) -> JSONResponse:
        logger.error("Storage error: %s", exc)
        return create_error_response(status.HTTP_503_SERVICE_UNAVAILABLE, "STORAGE_ERROR", "Blockchain storage failure")

    @app.exception_handler(Exception)
    async def generic_exception_handler(request: Request, exc: Exception) -> JSONResponse:
        logger.exception("Unexpected server error: %s", exc)
        return create_error_response(status.HTTP_500_INTERNAL_SERVER_ERROR, "INTERNAL_ERROR", "An unexpected server error occurred")
