"""Regression tests for admin credentials and the supported API launcher."""

from __future__ import annotations

import asyncio
import runpy
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest
from httpx import ASGITransport, AsyncClient
from pydantic import ValidationError

from api.app import create_app
from api.config import ApiConfig
from api.dependencies import get_node


@pytest.mark.parametrize("token", ["", " ", "secret token", "secret\t", "secret\n", "\x00", "\x7f", "mật-khẩu", "café"])
def test_invalid_configured_admin_token_fails_at_configuration(token):
    with pytest.raises(ValidationError, match="printable ASCII"):
        ApiConfig(
            _env_file=None,
            enable_admin_routes=True,
            demo_mode=True,
            admin_token=token,
        )


def test_printable_ascii_admin_token_is_preserved():
    token = "Secret-._~+/=123!"
    config = ApiConfig(_env_file=None, enable_admin_routes=True, demo_mode=True, admin_token=token)
    assert config.admin_token == token


@pytest.mark.parametrize(
    ("authorization", "expected_status", "expected_code"),
    [
        (None, 401, "UNAUTHORIZED"),
        (b"Basic secret-token", 401, "UNAUTHORIZED"),
        (b"Bearer ", 403, "FORBIDDEN"),
        (b"Bearer wrong-token", 403, "FORBIDDEN"),
        (b"Bearer secret-token ", 403, "FORBIDDEN"),
        (b"Bearer secret token", 403, "FORBIDDEN"),
        (b"Bearer secret\t", 403, "FORBIDDEN"),
        (b"Bearer \x00", 403, "FORBIDDEN"),
        (b"Bearer \x7f", 403, "FORBIDDEN"),
        (b"Bearer \xff", 403, "FORBIDDEN"),
        ("Bearer mật-khẩu".encode("utf-8"), 403, "FORBIDDEN"),
        (b"Bearer secret-token", 200, None),
    ],
)
def test_admin_auth_handles_malformed_header_without_internal_error(
    authorization, expected_status, expected_code
):
    async def scenario():
        config = ApiConfig(
            _env_file=None,
            enable_admin_routes=True,
            demo_mode=True,
            admin_token="secret-token",
        )
        app = create_app(config)
        node = SimpleNamespace(validate_chain=AsyncMock(return_value=True))
        app.dependency_overrides[get_node] = lambda: node
        headers = [] if authorization is None else [(b"authorization", authorization)]

        # No lifespan or socket is needed: the route's Node dependency is a stub.
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            response = await client.post("/api/v1/admin/validate-chain", headers=headers)

        assert response.status_code == expected_status
        if expected_code is None:
            assert response.json() == {"valid": True}
            node.validate_chain.assert_awaited_once()
        else:
            assert response.json()["error"]["code"] == expected_code
            node.validate_chain.assert_not_awaited()

    asyncio.run(scenario())


def test_launcher_keeps_proxy_and_websocket_safety_flags(monkeypatch):
    config = ApiConfig(
        _env_file=None,
        api_host="127.0.0.1",
        api_port=8765,
        ws_ping_interval=7.0,
        ws_idle_timeout=29.0,
        ws_max_message_bytes=1024,
    )
    run = Mock()
    monkeypatch.setattr("api.config.ApiConfig", lambda: config)
    monkeypatch.setattr("uvicorn.run", run)

    runpy.run_module("run_api", run_name="__main__")

    run.assert_called_once_with(
        "api.app:app",
        host="127.0.0.1",
        port=8765,
        reload=False,
        proxy_headers=False,
        ws_ping_interval=7.0,
        ws_ping_timeout=29.0,
        ws_max_size=1024,
    )
