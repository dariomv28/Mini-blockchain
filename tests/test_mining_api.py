"""Integration tests for Mining API endpoints, CSRF protection, and wallet balance updates."""

import asyncio
import pytest
from httpx import ASGITransport, AsyncClient

from api.app import create_app
from api.config import ApiConfig
from tests.phase11_helpers import application, csrf, login, register


@pytest.mark.anyio
async def test_mining_api_template_preview_and_job_execution():
    async with application() as (app, client):
        user_reg = await register(client, "miner_alice")
        miner_addr = user_reg["wallet"]["address"]
        assert (await login(client, "miner_alice")).status_code == 200

        # 1. Test POST /api/v1/mining/template
        tpl_res = await client.post("/api/v1/mining/template", json={"max_transactions": 50, "max_bytes": 50000})
        assert tpl_res.status_code == 200, tpl_res.text
        tpl_data = tpl_res.json()
        assert tpl_data["miner_address"] == miner_addr
        assert tpl_data["subsidy"] == 50
        assert tpl_data["fees"] == 0
        assert tpl_data["total_reward"] == 50
        assert tpl_data["template_height"] == 1

        # 2. Test CSRF enforcement on POST /api/v1/mining/jobs
        no_csrf_res = await client.post("/api/v1/mining/jobs", json={"max_nonce": 100_000})
        assert no_csrf_res.status_code == 403

        # 3. Start mining job with valid CSRF
        csrf_headers = await csrf(client)
        start_res = await client.post("/api/v1/mining/jobs", headers=csrf_headers, json={"max_nonce": 100_000})
        assert start_res.status_code == 201, start_res.text
        start_data = start_res.json()
        assert "job_id" in start_data
        job_id = start_data["job_id"]
        assert start_data["status"] in ("QUEUED", "MINING")

        # 4. Query GET /api/v1/mining/jobs/{job_id}
        status_res = await client.get(f"/api/v1/mining/jobs/{job_id}")
        assert status_res.status_code == 200
        assert status_res.json()["miner_address"] == miner_addr

        # 5. Wait for mining job to complete
        for _ in range(50):
            job_status = (await client.get(f"/api/v1/mining/jobs/{job_id}")).json()
            if job_status["status"] in ("ACCEPTED", "FAILED", "STALE"):
                break
            await asyncio.sleep(0.1)

        assert job_status["status"] == "ACCEPTED"
        assert job_status["accepted"] is True
        assert job_status["result_hash"] is not None

        # 6. Verify wallet summary updated with the 50 PYC reward!
        wallet_res = await client.get("/api/v1/wallet")
        assert wallet_res.status_code == 200
        summary = wallet_res.json()
        assert summary["confirmed_balance"] == 50
        assert summary["available_balance"] == 50


@pytest.mark.anyio
async def test_mining_api_cancel_job():
    async with application() as (app, client):
        await register(client, "miner_bob")
        assert (await login(client, "miner_bob")).status_code == 200
        csrf_headers = await csrf(client)

        # Start job with very high nonce to keep it running
        start_res = await client.post("/api/v1/mining/jobs", headers=csrf_headers, json={"max_nonce": 10_000_000})
        assert start_res.status_code == 201
        job_id = start_res.json()["job_id"]

        # Cancel with CSRF
        cancel_res = await client.delete(f"/api/v1/mining/jobs/{job_id}", headers=csrf_headers)
        assert cancel_res.status_code == 200
        assert cancel_res.json()["cancelled"] is True

        # Check job status is cancelled
        for _ in range(30):
            job_status = (await client.get(f"/api/v1/mining/jobs/{job_id}")).json()
            if job_status["status"] == "CANCELLED":
                break
            await asyncio.sleep(0.1)

        assert job_status["status"] == "CANCELLED"
