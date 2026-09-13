"""Tests for API lifecycle management and SQLite restart persistence."""

from __future__ import annotations

import asyncio
from pathlib import Path
from httpx import ASGITransport, AsyncClient
from ecdsa import SECP256k1, SigningKey

from blockchain.genesis import GENESIS_TIMESTAMP
from crypto.address import public_key_to_address
from mining.miner import mine_block
from api.app import create_app
from api.config import ApiConfig


def test_api_lifecycle_and_sqlite_persistence(tmp_path: Path):
    async def scenario():
        db_file = tmp_path / "api_persistence_test.sqlite3"
        config = ApiConfig(
            node_port=0,
            node_db=str(db_file),
            demo_mode=True,
        )

        miner_key = SigningKey.from_secret_exponent(701, curve=SECP256k1)
        miner_addr = public_key_to_address(miner_key.get_verifying_key())

        # Session 1: Start node via API, mine 2 blocks, record tip
        app1 = create_app(config)
        tip_hash_session1 = None
        async with app1.router.lifespan_context(app1):
            assert app1.state.node.state == "RUNNING"
            node1 = app1.state.node

            # Mine block 1
            t1 = await node1.create_mempool_block_template(miner_addr, timestamp=GENESIS_TIMESTAMP + 10)
            b1 = mine_block(t1, max_nonce=100_000)
            assert await node1.accept_block(b1)

            # Mine block 2
            t2 = await node1.create_mempool_block_template(miner_addr, timestamp=GENESIS_TIMESTAMP + 20)
            b2 = mine_block(t2, max_nonce=100_000)
            assert await node1.accept_block(b2)

            status1 = await node1.get_status()
            assert status1["height"] == 2
            tip_hash_session1 = status1["tip_hash"]

            async with AsyncClient(transport=ASGITransport(app=app1), base_url="http://test") as client1:
                res_tip = await client1.get("/api/v1/blocks/latest")
                assert res_tip.status_code == 200
                assert res_tip.json()["height"] == 2
                assert res_tip.json()["hash"] == tip_hash_session1

                # Submit an unconfirmed transaction to mempool before shutdown
                from transaction.transaction import Transaction
                from transaction.tx_input import TxInput
                from transaction.tx_output import TxOutput

                pending_tx = Transaction(
                    [TxInput(b1.transactions[0].txid(), 0)],
                    [TxOutput(45, miner_addr)],
                    timestamp=GENESIS_TIMESTAMP + 25,
                )
                pending_tx.sign_input(0, miner_key)
                tx_payload = {
                    "version": 1,
                    "timestamp": pending_tx.timestamp,
                    "inputs": [
                        {
                            "previous_tx_id": pending_tx.inputs[0].previous_tx_id,
                            "output_index": pending_tx.inputs[0].output_index,
                            "public_key": pending_tx.inputs[0].public_key,
                            "signature": pending_tx.inputs[0].signature,
                        }
                    ],
                    "outputs": [
                        {
                            "amount": pending_tx.outputs[0].amount,
                            "recipient_address": pending_tx.outputs[0].recipient_address,
                        }
                    ],
                }
                res_submit = await client1.post("/api/v1/transactions", json=tx_payload)
                assert res_submit.status_code == 201
                assert res_submit.json()["accepted"] is True
                assert res_submit.json()["txid"] == pending_tx.txid()

                res_mempool1 = await client1.get("/api/v1/mempool")
                assert res_mempool1.status_code == 200
                assert res_mempool1.json()["count"] == 1
                assert res_mempool1.json()["transactions"][0]["txid"] == pending_tx.txid()

        # Node should be cleanly stopped after exiting lifespan
        assert app1.state.node.state in {"STOPPING", "STOPPED"}

        # Session 2: Start new API instance pointing to same SQLite database
        app2 = create_app(config)
        async with app2.router.lifespan_context(app2):
            assert app2.state.node.state == "RUNNING"
            async with AsyncClient(transport=ASGITransport(app=app2), base_url="http://test") as client2:
                # Chain height and tip should be preserved across restart
                res_tip2 = await client2.get("/api/v1/blocks/latest")
                assert res_tip2.status_code == 200
                assert res_tip2.json()["height"] == 2
                assert res_tip2.json()["hash"] == tip_hash_session1

                # Blocks by height should be accessible
                res_b1 = await client2.get("/api/v1/blocks/1")
                assert res_b1.status_code == 200
                assert res_b1.json()["hash"] == b1.hash()

                res_b2 = await client2.get("/api/v1/blocks/2")
                assert res_b2.status_code == 200
                assert res_b2.json()["hash"] == b2.hash()

                # Balance of miner should be preserved (2 coinbase rewards = 100 PYC)
                res_bal = await client2.get(f"/api/v1/addresses/{miner_addr}/balance")
                assert res_bal.status_code == 200
                assert res_bal.json()["confirmed_balance"] == 100

                # Mempool unconfirmed transaction must be restored from SQLite across restart
                res_mempool2 = await client2.get("/api/v1/mempool")
                assert res_mempool2.status_code == 200
                assert res_mempool2.json()["count"] == 1
                assert res_mempool2.json()["transactions"][0]["txid"] == pending_tx.txid()

                # Mine block 3 including the restored pending transaction
                node2 = app2.state.node
                t3 = await node2.create_mempool_block_template(miner_addr, timestamp=GENESIS_TIMESTAMP + 35)
                assert len(t3.transactions) == 2  # coinbase + restored pending tx
                b3 = mine_block(t3, max_nonce=100_000)
                assert await node2.accept_block(b3)

                # After confirmation, mempool should be empty and height is 3
                res_mempool3 = await client2.get("/api/v1/mempool")
                assert res_mempool3.status_code == 200
                assert res_mempool3.json()["count"] == 0

                res_tip3 = await client2.get("/api/v1/blocks/latest")
                assert res_tip3.status_code == 200
                assert res_tip3.json()["height"] == 3
                assert res_tip3.json()["hash"] == b3.hash()

        assert app2.state.node.state in {"STOPPING", "STOPPED"}

    asyncio.run(scenario())
