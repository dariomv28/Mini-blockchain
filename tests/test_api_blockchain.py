"""Tests for blockchain query and transaction submission endpoints."""

from __future__ import annotations

import asyncio
from httpx import ASGITransport, AsyncClient
from ecdsa import SECP256k1, SigningKey

from blockchain.genesis import GENESIS_HASH, GENESIS_TIMESTAMP
from crypto.address import public_key_to_address
from mining.miner import mine_block
from transaction.transaction import Transaction
from transaction.tx_input import TxInput
from transaction.tx_output import TxOutput
from api.app import create_app
from api.config import ApiConfig


def test_blockchain_endpoints_and_submit():
    async def scenario():
        config = ApiConfig(node_port=0, node_db=None, demo_mode=True)
        app = create_app(config)

        # Setup keypairs for test
        alice_key = SigningKey.from_secret_exponent(501, curve=SECP256k1)
        bob_key = SigningKey.from_secret_exponent(502, curve=SECP256k1)
        alice_addr = public_key_to_address(alice_key.get_verifying_key())
        bob_addr = public_key_to_address(bob_key.get_verifying_key())

        async with app.router.lifespan_context(app):
            node = app.state.node
            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
                # 1. Latest block (genesis)
                res = await client.get("/api/v1/blocks/latest")
                assert res.status_code == 200
                genesis_data = res.json()
                assert genesis_data["height"] == 0
                assert genesis_data["hash"] == GENESIS_HASH
                assert genesis_data["transaction_count"] == 0

                # 2. Block by height
                res_b0 = await client.get("/api/v1/blocks/0")
                assert res_b0.status_code == 200
                assert res_b0.json()["hash"] == GENESIS_HASH

                res_b999 = await client.get("/api/v1/blocks/999")
                assert res_b999.status_code == 404
                assert res_b999.json()["error"]["code"] == "BLOCK_NOT_FOUND"

                # 3. Block by hash
                res_hash = await client.get(f"/api/v1/blocks/hash/{GENESIS_HASH}")
                assert res_hash.status_code == 200
                assert res_hash.json()["height"] == 0

                fake_hash = "a" * 64
                res_fake = await client.get(f"/api/v1/blocks/hash/{fake_hash}")
                assert res_fake.status_code == 404
                assert res_fake.json()["error"]["code"] == "BLOCK_NOT_FOUND"

                res_bad_hash = await client.get("/api/v1/blocks/hash/not-a-hash")
                assert res_bad_hash.status_code == 400
                assert res_bad_hash.json()["error"]["code"] == "INVALID_HASH"

                # 4. Block list
                res_list = await client.get("/api/v1/blocks?start=0&limit=10")
                assert res_list.status_code == 200
                assert len(res_list.json()) == 1

                # 5. Addresses and balances
                res_bal = await client.get(f"/api/v1/addresses/{alice_addr}/balance")
                assert res_bal.status_code == 200
                assert res_bal.json()["confirmed_balance"] == 0
                assert res_bal.json()["utxo_count"] == 0

                res_utxos = await client.get(f"/api/v1/addresses/{alice_addr}/utxos")
                assert res_utxos.status_code == 200
                assert res_utxos.json() == []

                res_bad_addr = await client.get("/api/v1/addresses/invalid-address/balance")
                assert res_bad_addr.status_code == 400
                assert res_bad_addr.json()["error"]["code"] == "INVALID_ADDRESS"

                # 6. Mempool initially empty
                res_mem = await client.get("/api/v1/mempool")
                assert res_mem.status_code == 200
                assert res_mem.json()["count"] == 0
                assert res_mem.json()["transactions"] == []

                # 7. Non-existent transaction query
                res_tx_fake = await client.get(f"/api/v1/transactions/{fake_hash}")
                assert res_tx_fake.status_code == 404
                assert res_tx_fake.json()["error"]["code"] == "TRANSACTION_NOT_FOUND"

                # 8. Mine a block to fund Alice
                template = await node.create_mempool_block_template(
                    alice_addr,
                    timestamp=GENESIS_TIMESTAMP + 1,
                    max_transactions=0,
                )
                mined = mine_block(template, max_nonce=100_000)
                assert mined is not None
                assert await node.accept_block(mined)

                funding_txid = mined.transactions[0].txid()
                res_tx_funding = await client.get(f"/api/v1/transactions/{funding_txid}")
                assert res_tx_funding.status_code == 200
                assert res_tx_funding.json()["status"] == "confirmed"
                assert res_tx_funding.json()["height"] == 1


                # Check Alice balance after funding
                res_alice_bal = await client.get(f"/api/v1/addresses/{alice_addr}/balance")
                assert res_alice_bal.status_code == 200
                assert res_alice_bal.json()["confirmed_balance"] == 50
                assert res_alice_bal.json()["utxo_count"] == 1

                # Get Alice's UTXO
                res_alice_utxos = await client.get(f"/api/v1/addresses/{alice_addr}/utxos")
                assert len(res_alice_utxos.json()) == 1
                utxo = res_alice_utxos.json()[0]

                # 9. Create and sign a transaction: Alice -> Bob (10 PYC, fee 1, change 39)
                tx = Transaction(
                    inputs=[TxInput(utxo["txid"], utxo["output_index"])],
                    outputs=[
                        TxOutput(10, bob_addr),
                        TxOutput(39, alice_addr),
                    ],
                    timestamp=GENESIS_TIMESTAMP + 2,
                )
                tx.sign_input(0, alice_key)

                # Submit signed transaction via REST API
                submit_payload = {
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

                res_submit = await client.post("/api/v1/transactions", json=submit_payload)
                assert res_submit.status_code == 201
                submit_data = res_submit.json()
                assert submit_data["accepted"] is True
                assert submit_data["status"] == "pending"
                txid = submit_data["txid"]

                # 10. Query mempool again
                res_mem2 = await client.get("/api/v1/mempool")
                assert res_mem2.status_code == 200
                assert res_mem2.json()["count"] == 1
                assert res_mem2.json()["transactions"][0]["txid"] == txid

                # 11. Query pending transaction by txid
                res_tx_pending = await client.get(f"/api/v1/transactions/{txid}")
                assert res_tx_pending.status_code == 200
                assert res_tx_pending.json()["status"] == "pending"
                assert res_tx_pending.json()["height"] is None

                # 12. Submit duplicate transaction -> rejected 422
                res_dup = await client.post("/api/v1/transactions", json=submit_payload)
                assert res_dup.status_code == 422
                assert res_dup.json()["error"]["code"] == "TRANSACTION_REJECTED"

                # 13. Submit malformed transaction -> 400
                res_malformed = await client.post("/api/v1/transactions", json={"version": 1})
                assert res_malformed.status_code == 400
                assert res_malformed.json()["error"]["code"] == "VALIDATION_ERROR"

                # 14. Strict schema validation tests (no coercion of bool/float/str, no extra fields)
                # 14a. Boolean instead of int
                bad_bool = dict(submit_payload, version=True)
                assert (await client.post("/api/v1/transactions", json=bad_bool)).status_code == 400

                # 14b. Float instead of int
                bad_float = dict(submit_payload, timestamp=12345.67)
                assert (await client.post("/api/v1/transactions", json=bad_float)).status_code == 400

                # 14c. String instead of int
                bad_str = dict(submit_payload, version="1")
                assert (await client.post("/api/v1/transactions", json=bad_str)).status_code == 400

                # 14d. Extra forbidden field
                bad_extra = dict(submit_payload, unexpected="hacker")
                assert (await client.post("/api/v1/transactions", json=bad_extra)).status_code == 400

                # 15. Pagination strict bounds
                assert (await client.get("/api/v1/blocks?start=0&limit=0")).status_code == 400
                assert (await client.get("/api/v1/blocks?start=0&limit=101")).status_code == 400
                assert (await client.get("/api/v1/blocks?start=-1&limit=10")).status_code == 400

    asyncio.run(scenario())

