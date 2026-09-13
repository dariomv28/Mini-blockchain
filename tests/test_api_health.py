"""Tests for API health and node status endpoints."""

from __future__ import annotations

import asyncio
from httpx import ASGITransport, AsyncClient
from api.app import create_app
from api.config import ApiConfig


def test_health_and_status():
    async def scenario():
        config = ApiConfig(
            node_port=0,
            node_db=None,
            demo_mode=True,
        )
        app = create_app(config)

        async with app.router.lifespan_context(app):
            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
                # 1. Health endpoint
                res = await client.get("/api/v1/health")
                assert res.status_code == 200
                data = res.json()
                assert data["status"] == "ok"
                assert data["node_state"] == "RUNNING"

                # 2. Node status endpoint
                res_status = await client.get("/api/v1/node/status")
                assert res_status.status_code == 200
                status_data = res_status.json()
                assert status_data["state"] == "RUNNING"
                assert status_data["height"] == 0  # Only genesis
                assert "tip_hash" in status_data
                assert status_data["pending_count"] == 0
                assert isinstance(status_data["peers"], list)

    asyncio.run(scenario())
