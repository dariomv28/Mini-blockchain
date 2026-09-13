"""Tests for admin endpoints (template/submission) and P2P transaction propagation."""

from __future__ import annotations

import asyncio
from pathlib import Path
from httpx import ASGITransport, AsyncClient

from blockchain.genesis import GENESIS_TIMESTAMP
from mining.miner import mine_block
from network import Node, NodeConfig
from network_worker import (
    ALICE, BOB, KEYS, close_nodes, mine, transfer, wait_status,
)
from api.app import create_app
from api.config import ApiConfig


def test_admin_block_template_and_submission(tmp_path: Path):
    async def scenario():
        admin_token = "super-secret-admin-token-12345"
        config = ApiConfig(
            node_port=0,
            node_db=str(tmp_path / "admin_api.sqlite3"),
            demo_mode=True,
            enable_admin_routes=True,
            admin_token=admin_token,
        )

        app = create_app(config)
        async with app.router.lifespan_context(app):
            node = app.state.node
            assert node.state == "RUNNING"

            # Mine an initial block locally to have a known chain tip
            b1 = await mine(node, ALICE)
            tip1 = (await node.get_status())["tip_hash"]
            assert (await node.get_status())["height"] == 1

            auth_headers = {"Authorization": f"Bearer {admin_token}"}
            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
                # 1. Test POST /api/v1/admin/blocks/template
                template_req = {
                    "miner_address": BOB,
                    "max_transactions": 50,
                    "max_bytes": 50000,
                }
                res_tpl = await client.post("/api/v1/admin/blocks/template", json=template_req, headers=auth_headers)
                assert res_tpl.status_code == 200
                tpl_data = res_tpl.json()
                assert "header" in tpl_data
                assert "transactions" in tpl_data
                assert tpl_data["header"]["previous_block_hash"] == tip1
                assert tpl_data["header"]["nonce"] == 0
                assert len(tpl_data["transactions"]) >= 1  # Coinbase

                # Generating a template should NOT alter chain height or mempool state
                status_after_tpl = await node.get_status()
                assert status_after_tpl["height"] == 1
                assert status_after_tpl["tip_hash"] == tip1
                assert status_after_tpl["pending_count"] == 0

                # 2. Mine a block based on node's template and submit via POST /api/v1/admin/blocks
                template = await node.create_mempool_block_template(
                    BOB, timestamp=GENESIS_TIMESTAMP + 10,
                )
                mined_block = mine_block(template, max_nonce=100_000)
                assert mined_block is not None

                block_payload = {
                    "header": {
                        "version": mined_block.version,
                        "previous_block_hash": mined_block.previous_block_hash,
                        "merkle_root": mined_block.merkle_root,
                        "timestamp": mined_block.timestamp,
                        "difficulty": mined_block.difficulty,
                        "nonce": mined_block.nonce,
                    },
                    "transactions": [
                        {
                            "version": tx.version,
                            "timestamp": tx.timestamp,
                            "inputs": [
                                {
                                    "previous_tx_id": inp.previous_tx_id,
                                    "output_index": inp.output_index,
                                    "public_key": inp.public_key,
                                    "signature": inp.signature,
                                }
                                for inp in tx.inputs
                            ],
                            "outputs": [
                                {
                                    "amount": out.amount,
                                    "recipient_address": out.recipient_address,
                                }
                                for out in tx.outputs
                            ],
                        }
                        for tx in mined_block.transactions
                    ],
                }

                # Submit valid mined block
                res_sub = await client.post("/api/v1/admin/blocks", json=block_payload, headers=auth_headers)
                assert res_sub.status_code == 201
                assert res_sub.json()["accepted"] is True
                assert res_sub.json()["hash"] == mined_block.hash()

                # Verify height updated
                status_after_mine = await node.get_status()
                assert status_after_mine["height"] == 2
                assert status_after_mine["tip_hash"] == mined_block.hash()

                # 3. Test Declared Merkle root mismatch -> 400 INVALID_MERKLE_ROOT
                mismatched_payload = dict(block_payload)
                mismatched_header = dict(block_payload["header"])
                mismatched_header["merkle_root"] = "0" * 64
                mismatched_payload["header"] = mismatched_header

                res_bad_merkle = await client.post(
                    "/api/v1/admin/blocks", json=mismatched_payload, headers=auth_headers,
                )
                assert res_bad_merkle.status_code == 400
                assert res_bad_merkle.json()["error"]["code"] == "INVALID_MERKLE_ROOT"

                # 4. Test Stale parent / invalid PoW -> 422 BLOCK_REJECTED
                bad_parent_payload = dict(block_payload)
                bad_parent_header = dict(block_payload["header"])
                bad_parent_header["previous_block_hash"] = "1" * 64
                bad_parent_payload["header"] = bad_parent_header

                res_bad_parent = await client.post(
                    "/api/v1/admin/blocks", json=bad_parent_payload, headers=auth_headers,
                )
                assert res_bad_parent.status_code == 422
                assert res_bad_parent.json()["error"]["code"] == "BLOCK_REJECTED"

    asyncio.run(scenario())


def test_api_p2p_transaction_propagation(tmp_path: Path):
    """Submitting a transaction to Node A via Web API propagates it to Node B over P2P."""
    async def scenario():
        db_a = tmp_path / "node_a.sqlite3"
        db_b = tmp_path / "node_b.sqlite3"

        config_a = ApiConfig(
            node_port=0,
            node_db=str(db_a),
            demo_mode=True,
        )

        app_a = create_app(config_a)
        node_b = None

        async with app_a.router.lifespan_context(app_a):
            node_a = app_a.state.node
            assert node_a.state == "RUNNING"
            assert node_a.endpoint is not None

            # Start independent Node B
            node_b = Node(NodeConfig(
                port=0,
                db_path=str(db_b),
                seeds=(),
                request_timeout=1.0,
                status_interval=0.2,
                mempool_refresh_interval=0.3,
                maintenance_interval=0.02,
            ))
            await node_b.start()

            try:
                # Connect Node B to Node A
                assert await node_b.connect(*node_a.endpoint)
                await wait_status(node_a, lambda s: len(s["peers"]) == 1)
                await wait_status(node_b, lambda s: len(s["peers"]) == 1)

                # Fund ALICE by mining block 1 on Node A
                b1 = await mine(node_a, ALICE)
                # Node B should sync block 1
                await wait_status(node_b, lambda s: s["height"] == 1)

                # Create a signed transaction from ALICE to BOB
                tx = transfer(b1.transactions[0], key=KEYS[0], outputs=[(45, BOB)], timestamp=GENESIS_TIMESTAMP + 20)
                tx_payload = {
                    "version": 1,
                    "timestamp": tx.timestamp,
                    "inputs": [
                        {
                            "previous_tx_id": tx.inputs[0].previous_tx_id,
                            "output_index": tx.inputs[0].output_index,
                            "public_key": tx.inputs[0].public_key,
                            "signature": tx.inputs[0].signature,
                        }
                    ],
                    "outputs": [
                        {
                            "amount": tx.outputs[0].amount,
                            "recipient_address": tx.outputs[0].recipient_address,
                        }
                    ],
                }

                # Submit transaction to Node A via REST API
                async with AsyncClient(transport=ASGITransport(app=app_a), base_url="http://test") as client_a:
                    res_submit = await client_a.post("/api/v1/transactions", json=tx_payload)
                    assert res_submit.status_code == 201
                    assert res_submit.json()["accepted"] is True
                    assert res_submit.json()["txid"] == tx.txid()

                # Node A should have the transaction in its mempool
                await wait_status(node_a, lambda s: s["pending_count"] == 1)

                # Node B should receive and admit the transaction via P2P gossip
                await wait_status(node_b, lambda s: s["pending_count"] == 1)
                pending_b = await node_b.get_pending_transactions()
                assert len(pending_b) == 1
                assert pending_b[0].txid() == tx.txid()

            finally:
                if node_b is not None:
                    await node_b.stop()

    asyncio.run(scenario())
