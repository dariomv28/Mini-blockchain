"""Tests for API security boundaries: size limits, rate limits, admin auth, CORS, and WebSocket hardening."""

from __future__ import annotations

import asyncio
import pytest
from httpx import ASGITransport, AsyncClient
from starlette.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

from api.app import create_app
from api.config import ApiConfig


def test_request_size_limit_content_length_and_chunked():
    async def scenario():
        config = ApiConfig(
            node_port=0,
            node_db=None,
            max_body_bytes=100,
            demo_mode=True,
            frontend_origin="http://allowed.local",
        )
        app = create_app(config)

        async with app.router.lifespan_context(app):
            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
                # 1. Stated Content-Length exceeds limit -> 413 with CORS
                res_cl = await client.post(
                    "/api/v1/transactions",
                    content=b"x" * 150,
                    headers={
                        "content-length": "150",
                        "Origin": "http://allowed.local",
                    },
                )
                assert res_cl.status_code == 413
                assert res_cl.json()["error"]["code"] == "REQUEST_TOO_LARGE"
                assert res_cl.headers.get("access-control-allow-origin") == "http://allowed.local"

                # 2. Invalid Content-Length -> 400
                res_bad_cl = await client.post(
                    "/api/v1/transactions",
                    content=b"test",
                    headers={"content-length": "notanumber"},
                )
                assert res_bad_cl.status_code == 400
                assert res_bad_cl.json()["error"]["code"] == "INVALID_CONTENT_LENGTH"

                # 3. Chunked / stream-without-content-length exceeds limit -> 413
                async def chunk_generator():
                    yield b"a" * 60
                    yield b"b" * 60

                res_chunked = await client.post(
                    "/api/v1/transactions",
                    content=chunk_generator(),
                    headers={"Origin": "http://allowed.local"},
                )
                assert res_chunked.status_code == 413
                assert res_chunked.json()["error"]["code"] == "REQUEST_TOO_LARGE"

    asyncio.run(scenario())


def test_rate_limiter_tiered_and_no_upgrade_bypass():
    async def scenario():
        config = ApiConfig(
            node_port=0,
            node_db=None,
            rate_limit_per_minute=10,
            rate_limit_mutation_per_minute=3,
            rate_limit_admin_per_minute=2,
            enable_admin_routes=True,
            admin_token="secret-token",
            demo_mode=True,
            frontend_origin="http://allowed.local",
        )
        app = create_app(config)

        async with app.router.lifespan_context(app):
            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
                # 1. Mutation quota limit is 3. Sending 3 POSTs:
                for _ in range(3):
                    res = await client.post("/api/v1/transactions", json={"dummy": 1})
                    # Will be 400 validation error, but counts toward quota
                    assert res.status_code == 400

                # 4th POST should be blocked by mutation quota -> 429
                res_mut_blocked = await client.post(
                    "/api/v1/transactions",
                    json={"dummy": 1},
                    headers={"Origin": "http://allowed.local"},
                )
                assert res_mut_blocked.status_code == 429
                assert res_mut_blocked.json()["error"]["code"] == "RATE_LIMITED"
                assert "Retry-After" in res_mut_blocked.headers
                assert res_mut_blocked.headers.get("access-control-allow-origin") == "http://allowed.local"

                # 2. Adding Upgrade: websocket MUST NOT bypass rate limit
                res_fake_ws = await client.post(
                    "/api/v1/transactions",
                    json={"dummy": 1},
                    headers={"Upgrade": "websocket"},
                )
                assert res_fake_ws.status_code == 429

                # 3. GET requests (non-mutation) still have general quota remaining
                res_get = await client.get("/api/v1/health")
                assert res_get.status_code == 200

    asyncio.run(scenario())


def test_admin_routes_matrix():
    async def scenario():
        # Case A: Disabled admin routes -> 404
        cfg_disabled = ApiConfig(node_port=0, enable_admin_routes=False, demo_mode=True)
        app_disabled = create_app(cfg_disabled)
        async with app_disabled.router.lifespan_context(app_disabled):
            async with AsyncClient(transport=ASGITransport(app=app_disabled), base_url="http://test") as client:
                res = await client.post("/api/v1/admin/validate-chain")
                assert res.status_code == 404

        # Case B: Enabled admin routes with token
        cfg_enabled = ApiConfig(
            node_port=0,
            enable_admin_routes=True,
            admin_token="super-secret-admin-pass",
            demo_mode=True,
        )
        app_enabled = create_app(cfg_enabled)
        async with app_enabled.router.lifespan_context(app_enabled):
            async with AsyncClient(transport=ASGITransport(app=app_enabled), base_url="http://test") as client:
                # No token -> 401
                res_no_tok = await client.post("/api/v1/admin/validate-chain")
                assert res_no_tok.status_code == 401
                assert res_no_tok.json()["error"]["code"] == "UNAUTHORIZED"

                # Wrong token -> 403
                res_bad_tok = await client.post(
                    "/api/v1/admin/validate-chain",
                    headers={"Authorization": "Bearer wrong-pass"},
                )
                assert res_bad_tok.status_code == 403
                assert res_bad_tok.json()["error"]["code"] == "FORBIDDEN"

                # Correct token -> 200
                res_ok = await client.post(
                    "/api/v1/admin/validate-chain",
                    headers={"Authorization": "Bearer super-secret-admin-pass"},
                )
                assert res_ok.status_code == 200
                assert res_ok.json()["valid"] is True

    asyncio.run(scenario())


def test_websocket_hardening():
    config = ApiConfig(
        node_port=0,
        node_db=None,
        frontend_origin="http://trusted.local",
        ws_max_clients=2,
        ws_max_clients_per_ip=2,
        ws_max_message_bytes=100,
        demo_mode=True,
    )
    app = create_app(config)

    with TestClient(app) as client:
        # 1. Unauthorized origin rejected
        with pytest.raises(WebSocketDisconnect) as rejected:
            with client.websocket_connect("/api/v1/ws", headers={"Origin": "http://evil.com"}) as ws:
                pytest.fail("Unauthorized origin should be closed")
        assert rejected.value.code == 1008

        # 2. Authorized origin accepted and ping-pong works
        with client.websocket_connect("/api/v1/ws", headers={"Origin": "http://trusted.local"}) as ws:
            init_msg = ws.receive_json()
            assert init_msg["type"] == "node_status"

            ws.send_text("ping")
            reply = ws.receive_text()
            assert reply == "pong"

        # 3. Message exceeding 100 bytes is closed (1009)
        with client.websocket_connect("/api/v1/ws", headers={"Origin": "http://trusted.local"}) as ws:
            ws.receive_json()
            ws.send_text("x" * 200)
            with pytest.raises(WebSocketDisconnect) as oversized:
                ws.receive_text()
            assert oversized.value.code == 1009

        # 4. Binary frame rejected (1003)
        with client.websocket_connect("/api/v1/ws", headers={"Origin": "http://trusted.local"}) as ws:
            ws.receive_json()
            ws.send_bytes(b"\x00\x01\x02")
            with pytest.raises(WebSocketDisconnect) as binary:
                ws.receive_text()
            assert binary.value.code == 1003
