"""Unit tests for MiningService, background worker, cooperative cancel, and race condition handling."""

import asyncio
import pytest

from api.config import ApiConfig
from api.errors import APIError
from api.services.mining_service import MiningService
from network.config import NodeConfig
from network.node import Node
from tests.phase11_helpers import fund


@pytest.mark.anyio
async def test_candidate_template_generation_and_reward_derivation(tmp_path):
    node = Node(NodeConfig(port=0, db_path=str(tmp_path / "node.sqlite3")))
    await node.start()
    try:
        service = MiningService(node, None, ApiConfig(node_port=0, node_db=None))
        address = "PYC_3ffb8df06c0f1aaf5dc42e57b232f7ddca0d0f81beabbcea"
        template = await service.build_candidate_template(address)
        assert template["miner_address"] == address
        assert template["subsidy"] == 50
        assert template["fees"] == 0
        assert template["total_reward"] == 50
        assert template["difficulty"] == 16
        assert template["template_height"] == 1
    finally:
        await node.stop()


@pytest.mark.anyio
async def test_mining_service_worker_accepts_block_and_credits_miner(tmp_path):
    node = Node(NodeConfig(port=0, db_path=str(tmp_path / "node.sqlite3")))
    await node.start()
    try:
        service = MiningService(node, None, ApiConfig(node_port=0, node_db=None))
        address = "PYC_3ffb8df06c0f1aaf5dc42e57b232f7ddca0d0f81beabbcea"
        job = await service.create_job(user_id=1, miner_address=address, max_nonce=100_000)
        assert job.status in ("QUEUED", "MINING")

        # Wait for worker to finish
        for _ in range(50):
            if job.finished_at is not None:
                break
            await asyncio.sleep(0.1)

        assert job.status == "ACCEPTED"
        assert job.accepted is True
        assert job.result_hash is not None
        assert job.nonce is not None

        # Verify node height and balance
        status = await node.get_status()
        assert status["height"] == 1
        assert (await node.get_balance(address)) == 50
    finally:
        await service.close()
        await node.stop()


@pytest.mark.anyio
async def test_single_active_job_constraint(tmp_path):
    node = Node(NodeConfig(port=0, db_path=str(tmp_path / "node.sqlite3")))
    await node.start()
    try:
        service = MiningService(node, None, ApiConfig(node_port=0, node_db=None))
        address = "PYC_3ffb8df06c0f1aaf5dc42e57b232f7ddca0d0f81beabbcea"

        # Start job 1
        job1 = await service.create_job(user_id=1, miner_address=address, max_nonce=500_000)

        # Attempt to start job 2 while job 1 is active
        if job1.finished_at is None:
            with pytest.raises(APIError) as exc_info:
                await service.create_job(user_id=1, miner_address=address, max_nonce=100_000)
            assert exc_info.value.status_code == 409
            assert exc_info.value.code == "MINING_BUSY"

        # Wait for completion
        for _ in range(50):
            if job1.finished_at is not None:
                break
            await asyncio.sleep(0.1)
    finally:
        await service.close()
        await node.stop()


@pytest.mark.anyio
async def test_cooperative_cancellation(tmp_path):
    node = Node(NodeConfig(port=0, db_path=str(tmp_path / "node.sqlite3")))
    await node.start()
    try:
        # Configure large difficulty/nonce so it stays busy
        service = MiningService(node, None, ApiConfig(node_port=0, node_db=None, mining_progress_interval=10))
        address = "PYC_3ffb8df06c0f1aaf5dc42e57b232f7ddca0d0f81beabbcea"

        job = await service.create_job(user_id=1, miner_address=address, max_nonce=10_000_000)
        # Cancel right away
        res = await service.cancel_job(job.id, user_id=1)
        assert res["cancelled"] is True

        # Wait for worker task to detect cancellation and exit
        for _ in range(30):
            if job.finished_at is not None:
                break
            await asyncio.sleep(0.1)

        assert job.status == "CANCELLED"
    finally:
        await service.close()
        await node.stop()


@pytest.mark.anyio
async def test_stale_detection_on_race_condition(tmp_path):
    node = Node(NodeConfig(port=0, db_path=str(tmp_path / "node.sqlite3")))
    await node.start()
    try:
        service = MiningService(node, None, ApiConfig(node_port=0, node_db=None))
        miner_alice = "PYC_3ffb8df06c0f1aaf5dc42e57b232f7ddca0d0f81beabbcea"
        miner_bob = "PYC_b197cd7b19f4bcfd345626fdbf74b1e8c0f509b8871eeed3"

        # Build template at current tip (Genesis)
        template = await node.create_mempool_block_template(miner_alice)

        # Before mining finishes, Bob mines a block first and advances the tip!
        await fund(node, miner_bob)
        status_after_bob = await node.get_status()
        assert status_after_bob["height"] == 1

        # Now simulate mining the template that was created at Genesis
        from mining.miner import mine_block
        mined_stale = mine_block(template, max_nonce=100_000)
        assert mined_stale is not None

        # When submitted, node rejects because previous_block_hash does not match new tip
        accepted = await node.accept_block(mined_stale)
        assert accepted is False
    finally:
        await service.close()
        await node.stop()


@pytest.mark.anyio
async def test_cancel_job_authorization_forbidden(tmp_path):
    node = Node(NodeConfig(port=0, db_path=str(tmp_path / "node.sqlite3")))
    await node.start()
    try:
        service = MiningService(node, None, ApiConfig(node_port=0, node_db=None, mining_progress_interval=10))
        address = "PYC_3ffb8df06c0f1aaf5dc42e57b232f7ddca0d0f81beabbcea"
        job = await service.create_job(user_id=1, miner_address=address, max_nonce=10_000_000)

        # Bob (user_id=2) tries to cancel Alice's (user_id=1) job -> 403 Forbidden
        with pytest.raises(APIError) as exc_info:
            await service.cancel_job(job.id, user_id=2, is_admin=False)
        assert exc_info.value.status_code == 403
        assert exc_info.value.code == "FORBIDDEN"

        # Admin (is_admin=True) can cancel
        res_admin = await service.cancel_job(job.id, user_id=2, is_admin=True)
        assert res_admin["cancelled"] is True
        assert job.status == "CANCELLED"
        assert job.thread is None or not job.thread.is_alive()
    finally:
        await service.close()
        await node.stop()


@pytest.mark.anyio
async def test_accept_block_exception_handling(tmp_path):
    from unittest.mock import AsyncMock
    node = Node(NodeConfig(port=0, db_path=str(tmp_path / "node.sqlite3")))
    await node.start()
    try:
        service = MiningService(node, None, ApiConfig(node_port=0, node_db=None))
        address = "PYC_3ffb8df06c0f1aaf5dc42e57b232f7ddca0d0f81beabbcea"

        # Simulate storage / node crash during accept_block
        node.accept_block = AsyncMock(side_effect=RuntimeError("Simulated storage failure"))

        job = await service.create_job(user_id=1, miner_address=address, max_nonce=100_000)

        for _ in range(50):
            if job.finished_at is not None:
                break
            await asyncio.sleep(0.1)

        # Must not get stuck in FOUND; must be FAILED with error recorded
        assert job.status == "FAILED"
        assert job.accepted is False
        assert "Simulated storage failure" in (job.error or "")
    finally:
        await service.close()
        await node.stop()
