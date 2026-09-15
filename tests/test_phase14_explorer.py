"""Tests for Phase 14: Blockchain Explorer (Backend API, Caching, and Security)."""

import asyncio
import pytest

from phase11_helpers import application, csrf, fund, login, register


def test_explorer_requires_authentication():
    """All /api/v1/explorer/* endpoints must reject unauthenticated requests with 401."""
    async def scenario():
        async with application() as (app, guest_client):
            dummy_hash = "0" * 64
            dummy_addr = "PYC_dummy_address_12345678"

            endpoints = [
                "/api/v1/explorer/stats",
                "/api/v1/explorer/blocks",
                "/api/v1/explorer/blocks/height/0",
                f"/api/v1/explorer/blocks/hash/{dummy_hash}",
                f"/api/v1/explorer/transactions/{dummy_hash}",
                f"/api/v1/explorer/addresses/{dummy_addr}",
                "/api/v1/explorer/mempool",
                "/api/v1/explorer/search?q=0",
            ]

            for endpoint in endpoints:
                res = await guest_client.get(endpoint)
                assert res.status_code == 401, f"{endpoint} expected 401, got {res.status_code}: {res.text}"
                data = res.json()
                assert data["error"]["code"] == "UNAUTHORIZED"

    asyncio.run(scenario())


def test_explorer_chain_view_caching_and_invalidation():
    """ChainView is cached per tip_hash and rebuilt when a new block is mined."""
    async def scenario():
        async with application() as (app, client):
            alice = await register(client, "alice")
            alice_addr = alice["wallet"]["address"]
            assert (await login(client, "alice")).status_code == 200

            from api.services.explorer_service import explorer_service

            node = app.state.node
            # 1. Initial snapshot (Genesis only)
            view1 = await explorer_service.get_chain_view(node)
            assert view1.tip_height == 0
            assert view1.tip_hash != ""

            # 2. Second query with same tip must return cached instance
            view2 = await explorer_service.get_chain_view(node)
            assert view1 is view2

            # 3. Mine a new block -> tip changes
            await fund(node, alice_addr)

            # 4. Next query must rebuild and return updated instance
            view3 = await explorer_service.get_chain_view(node)
            assert view3 is not view1
            assert view3.tip_height == 1
            assert view3.tip_hash != view1.tip_hash

    asyncio.run(scenario())


def test_explorer_stats_and_blocks_pagination():
    """Authenticated user can fetch network stats and paginated blocks list."""
    async def scenario():
        async with application() as (app, client):
            alice = await register(client, "alice")
            alice_addr = alice["wallet"]["address"]
            await fund(app.state.node, alice_addr)
            assert (await login(client, "alice")).status_code == 200

            # 1. Stats
            stats_res = await client.get("/api/v1/explorer/stats")
            assert stats_res.status_code == 200, stats_res.text
            stats = stats_res.json()
            assert stats["height"] == 1
            assert len(stats["tip_hash"]) == 64
            assert stats["mempool_count"] == 0
            assert stats["total_confirmed_transactions"] == 1  # block 1 coinbase

            # 2. Blocks list
            blocks_res = await client.get("/api/v1/explorer/blocks?limit=10&offset=0")
            assert blocks_res.status_code == 200, blocks_res.text
            bdata = blocks_res.json()
            assert bdata["total_blocks"] == 2
            assert len(bdata["blocks"]) == 2
            # Descending order: height 1 then height 0
            assert bdata["blocks"][0]["height"] == 1
            assert bdata["blocks"][1]["height"] == 0
            assert bdata["blocks"][0]["miner_address"] == alice_addr
            assert bdata["blocks"][0]["size_bytes"] > 0

            # 3. Pagination limits validation
            bad_limit = await client.get("/api/v1/explorer/blocks?limit=51")
            assert bad_limit.status_code == 400
            assert bad_limit.json()["error"]["code"] in {"INVALID_PAGINATION", "VALIDATION_ERROR"}

            bad_offset = await client.get("/api/v1/explorer/blocks?offset=-1")
            assert bad_offset.status_code == 400
            assert bad_offset.json()["error"]["code"] in {"INVALID_PAGINATION", "VALIDATION_ERROR"}

    asyncio.run(scenario())


def test_explorer_block_detail_by_height_and_hash():
    """Block detail endpoint resolves both height and 64-hex hash."""
    async def scenario():
        async with application() as (app, client):
            alice = await register(client, "alice")
            alice_addr = alice["wallet"]["address"]
            await fund(app.state.node, alice_addr)
            assert (await login(client, "alice")).status_code == 200

            # Get genesis block by height 0 (genesis has 0 transactions)
            res0 = await client.get("/api/v1/explorer/blocks/height/0")
            assert res0.status_code == 200, res0.text
            blk0 = res0.json()
            assert blk0["height"] == 0
            assert blk0["transaction_count"] == 0

            genesis_hash = blk0["hash"]

            # Get genesis block by hash
            hash_res = await client.get(f"/api/v1/explorer/blocks/hash/{genesis_hash}")
            assert hash_res.status_code == 200, hash_res.text
            assert hash_res.json()["height"] == 0

            # Get block 1 by height (has 1 coinbase transaction)
            res1 = await client.get("/api/v1/explorer/blocks/height/1")
            assert res1.status_code == 200, res1.text
            blk1 = res1.json()
            assert blk1["height"] == 1
            assert blk1["transaction_count"] == 1
            assert len(blk1["transactions"]) == 1
            assert blk1["transactions"][0]["is_coinbase"] is True
            assert blk1["transactions"][0]["fee"] == 0
            assert blk1["miner_address"] == alice_addr

            # Nonexistent block height
            not_found_h = await client.get("/api/v1/explorer/blocks/height/9999")
            assert not_found_h.status_code == 404
            assert not_found_h.json()["error"]["code"] == "BLOCK_NOT_FOUND"

            # Nonexistent block hash
            not_found_hash = await client.get(f"/api/v1/explorer/blocks/hash/{'f'*64}")
            assert not_found_hash.status_code == 404

            # Malformed hash
            bad_hash = await client.get("/api/v1/explorer/blocks/hash/invalid-hash-123")
            assert bad_hash.status_code == 400
            assert bad_hash.json()["error"]["code"] == "INVALID_HASH"

    asyncio.run(scenario())


def test_explorer_transaction_and_mempool_lifecycle():
    """Tracks transaction detail from pending in mempool to confirmed in block, with resolved input addresses and fee."""
    async def scenario():
        async with application() as (app, client):
            a = await register(client, "alice")
            b = await register(client, "bob")
            alice_addr = a["wallet"]["address"]
            bob_addr = b["wallet"]["address"]

            # Fund alice with 50 PYC in block 1
            await fund(app.state.node, alice_addr)
            assert (await login(client, "alice")).status_code == 200

            # Alice sends 12 PYC to Bob with fee 2
            body = {"recipient_address": bob_addr, "amount": 12, "fee": 2}
            send_res = await client.post(
                "/api/v1/wallet/send",
                headers={**await csrf(client), "Idempotency-Key": "explorer-tx-1"},
                json=body,
            )
            assert send_res.status_code == 201, send_res.text
            txid = send_res.json()["txid"]

            # 1. Inspect mempool via Explorer
            mempool_res = await client.get("/api/v1/explorer/mempool")
            assert mempool_res.status_code == 200
            mempool = mempool_res.json()
            assert mempool["count"] == 1
            assert mempool["transactions"][0]["txid"] == txid
            assert mempool["transactions"][0]["fee"] == 2
            assert mempool["transactions"][0]["status"] == "pending"

            # 2. Inspect pending transaction detail via Explorer
            tx_res = await client.get(f"/api/v1/explorer/transactions/{txid}")
            assert tx_res.status_code == 200, tx_res.text
            tx_info = tx_res.json()
            assert tx_info["txid"] == txid
            assert tx_info["status"] == "pending"
            assert tx_info["block_height"] is None
            assert tx_info["fee"] == 2
            assert len(tx_info["inputs"]) >= 1
            # Verify resolved source address and amount
            assert tx_info["inputs"][0]["source_address"] == alice_addr
            assert tx_info["inputs"][0]["amount"] == 50
            # Outputs: 12 to Bob, 36 change to Alice
            assert any(o["recipient_address"] == bob_addr and o["amount"] == 12 for o in tx_info["outputs"])

            # 3. Mine the transaction into a block (block 2)
            from mining.miner import mine_block
            template = await app.state.node.create_mempool_block_template(alice_addr)
            block = mine_block(template, max_nonce=100_000)
            assert block is not None
            assert await app.state.node.accept_block(block)

            # 4. Verify transaction is now confirmed in block 2
            tx_conf_res = await client.get(f"/api/v1/explorer/transactions/{txid}")
            assert tx_conf_res.status_code == 200
            tx_conf = tx_conf_res.json()
            assert tx_conf["status"] == "confirmed"
            assert tx_conf["block_height"] == 2
            assert tx_conf["fee"] == 2

            # 5. Mempool is now empty
            mempool_after = await client.get("/api/v1/explorer/mempool")
            assert mempool_after.json()["count"] == 0

            # 6. Check Address Detail for Alice
            addr_res = await client.get(f"/api/v1/explorer/addresses/{alice_addr}")
            assert addr_res.status_code == 200, addr_res.text
            addr_data = addr_res.json()
            assert addr_data["address"] == alice_addr
            # Balance: +50 from funding (block 1), -14 (12 + 2 fee), +50 subsidy + 2 fee from mining block 2 = 88
            assert addr_data["confirmed_balance"] == 88
            assert addr_data["total_transactions"] >= 3
            # History contains sent and mined transactions
            directions = {t["direction"] for t in addr_data["transactions"]}
            assert "sent" in directions
            assert "mined" in directions

    asyncio.run(scenario())


def test_explorer_universal_search():
    """Search correctly classifies block height, block hash, txid, address, and unknown queries."""
    async def scenario():
        async with application() as (app, client):
            alice = await register(client, "alice")
            alice_addr = alice["wallet"]["address"]
            await fund(app.state.node, alice_addr)
            assert (await login(client, "alice")).status_code == 200

            # Get genesis block and block 1 info
            blk0 = (await client.get("/api/v1/explorer/blocks/height/0")).json()
            genesis_hash = blk0["hash"]

            blk1 = (await client.get("/api/v1/explorer/blocks/height/1")).json()
            coinbase_txid = blk1["transactions"][0]["txid"]

            # 1. Search by height number: "0"
            s1 = (await client.get("/api/v1/explorer/search?q=0")).json()
            assert s1["result_type"] == "block"
            assert s1["target_url"] == "/explorer/block/0"
            assert s1["payload"]["height"] == 0

            # 2. Search by block hash (64 hex)
            s2 = (await client.get(f"/api/v1/explorer/search?q={genesis_hash}")).json()
            assert s2["result_type"] == "block"
            assert s2["target_url"] == f"/explorer/block/{genesis_hash}"

            # 3. Search by txid (64 hex)
            s3 = (await client.get(f"/api/v1/explorer/search?q={coinbase_txid}")).json()
            assert s3["result_type"] == "transaction"
            assert s3["target_url"] == f"/explorer/tx/{coinbase_txid}"

            # 4. Search by PYC address
            s4 = (await client.get(f"/api/v1/explorer/search?q={alice_addr}")).json()
            assert s4["result_type"] == "address"
            assert s4["target_url"] == f"/explorer/address/{alice_addr}"

            # 5. Search unknown string
            s5 = (await client.get("/api/v1/explorer/search?q=unknown_target_xyz")).json()
            assert s5["result_type"] == "not_found"

    asyncio.run(scenario())


def test_explorer_search_unicode_digit_safe():
    """Searching Unicode digits like '²' or '①' must not crash with 500."""
    async def scenario():
        async with application() as (app, client):
            await register(client, "alice")
            assert (await login(client, "alice")).status_code == 200

            for q in ["²", "①", "½", "²³", "¼"]:
                res = await client.get(f"/api/v1/explorer/search?q={q}")
                assert res.status_code == 200, f"Expected 200 for query {q}, got {res.status_code}: {res.text}"
                data = res.json()
                assert data["result_type"] == "not_found"

    asyncio.run(scenario())


def test_explorer_batch_blocks_above_height_100():
    """ExplorerService.get_chain_view must batch requests of <= 100 blocks when height >= 100."""
    from unittest.mock import AsyncMock
    from api.services.explorer_service import ExplorerService
    from blockchain.block import Block

    async def scenario():
        service = ExplorerService()
        dummy_blocks = [
            Block(transactions=[], previous_block_hash="0" * 64, timestamp=1000 + i, version=1, difficulty=1, nonce=i)
            for i in range(105)
        ]

        mock_node = AsyncMock()
        mock_node.get_latest_block_info.return_value = {
            "block": dummy_blocks[-1],
            "height": 104,
        }

        async def mock_get_blocks(start_height: int, limit: int):
            # Enforce core node's strict limit <= 100
            assert limit <= 100, f"Core get_blocks called with limit {limit} > 100!"
            return dummy_blocks[start_height : start_height + limit]

        mock_node.get_blocks.side_effect = mock_get_blocks

        view = await service.get_chain_view(mock_node)
        assert view.tip_height == 104
        assert len(view.blocks_by_height) == 105
        assert 0 in view.blocks_by_height
        assert 104 in view.blocks_by_height

    asyncio.run(scenario())


def test_explorer_address_history_output_aggregation():
    """Multiple outputs to the same address in a single transaction must be aggregated into one record."""
    from transaction.transaction import Transaction
    from transaction.tx_output import TxOutput
    from blockchain.block import Block
    from api.services.explorer_service import ChainView

    view = ChainView(tip_height=1, tip_hash="0" * 64)
    bob_addr = "PYC_bob_wallet_address_12345678"

    # Block 0: Genesis
    b0 = Block(transactions=[], previous_block_hash="0" * 64, timestamp=100, version=1, difficulty=1, nonce=0)

    # Block 1: Coinbase transaction that pays Bob in two outputs: 5 PYC + 7 PYC
    tx = Transaction(
        inputs=[],
        outputs=[
            TxOutput(amount=5, recipient_address=bob_addr),
            TxOutput(amount=7, recipient_address=bob_addr),
        ],
        timestamp=200,
        version=1,
    )
    b1 = Block(transactions=[tx], previous_block_hash=b0.hash(), timestamp=200, version=1, difficulty=1, nonce=0)

    view.populate([b0, b1])

    bob_history = view.address_history.get(bob_addr, [])
    assert len(bob_history) == 1, f"Expected exactly 1 aggregated history item, got {len(bob_history)}"
    assert bob_history[0]["txid"] == tx.txid()
    assert bob_history[0]["amount"] == 12, f"Expected aggregated amount 12, got {bob_history[0]['amount']}"
    assert bob_history[0]["direction"] == "mined"

