"""FastAPI dependencies for node access, config, and admin security."""

from __future__ import annotations

import secrets
from fastapi import Depends, Header, Request, status
from network.node import Node
from api.config import ApiConfig
from api.errors import APIError


def get_config(request: Request) -> ApiConfig:
    config = getattr(request.app.state, "config", None)
    if config is None:
        raise APIError(status.HTTP_500_INTERNAL_SERVER_ERROR, "CONFIG_ERROR", "App configuration not initialized")
    return config


def get_node(request: Request) -> Node:
    node = getattr(request.app.state, "node", None)
    if node is None or getattr(node, "state", None) != "RUNNING":
        raise APIError(status.HTTP_503_SERVICE_UNAVAILABLE, "NODE_CLOSED", "Blockchain node is not running")
    return node


async def verify_admin_token(
    request: Request,
    authorization: str | None = Header(default=None),
    config: ApiConfig = Depends(get_config),
) -> bool:
    if not config.enable_admin_routes or not config.demo_mode:
        raise APIError(status.HTTP_404_NOT_FOUND, "NOT_FOUND", "Admin routes are disabled")

    # In strict admin mode, admin_token is mandatory
    if not config.admin_token or not config.admin_token.strip():
        raise APIError(status.HTTP_500_INTERNAL_SERVER_ERROR, "CONFIG_ERROR", "Admin token is not configured on server")

    if not authorization or not authorization.startswith("Bearer "):
        raise APIError(status.HTTP_401_UNAUTHORIZED, "UNAUTHORIZED", "Admin Bearer token required")

    token = authorization[len("Bearer "):]
    # HTTP header values can contain non-ASCII bytes. Validate before the
    # ASCII-only constant-time comparison instead of letting it raise a 500.
    if not token or not all("!" <= char <= "~" for char in token):
        raise APIError(status.HTTP_403_FORBIDDEN, "FORBIDDEN", "Invalid admin credentials")
    if not secrets.compare_digest(token, config.admin_token):
        raise APIError(status.HTTP_403_FORBIDDEN, "FORBIDDEN", "Invalid admin credentials")

    # Bearer-only native clients do not use ambient browser credentials. When
    # a browser session cookie is present, enforce its CSRF protection too.
    if request.cookies.get("pychain_session"):
        from auth.dependencies import verify_csrf
        await verify_csrf(request)

    return True
