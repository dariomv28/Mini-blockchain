"""Real TCP catch-up, dependency pages and adversarial response handling."""

import asyncio
from copy import deepcopy
import secrets

import pytest

from blockchain.blockchain import Blockchain
from blockchain.genesis import GENESIS_HASH, GENESIS_TIMESTAMP
from consensus.pow import validate_proof_of_work
from mining.miner import mine_block
from network import Node
from storage.codec import encode_transaction
from network_worker import (
    ALICE, CAROL, KEYS, MINER, WirePeer, close_nodes, config, item,
    mine, transfer, wait_status, wait_until,
)


def chain_blocks(count, address=ALICE):
    with Blockchain() as chain:
        result = []
        for height in range(1, count + 1):
            block = mine_block(chain.create_block_template(
                address, timestamp=GENESIS_TIMESTAMP + height,
            ), max_nonce=100_000)
            assert block is not None and chain.add_block(block)
            result.append(block)
        return result


async def respond_blocks(peer, request, blocks, tip, *, more=False):
    anchor = request["payload"]
    await peer.send("BLOCKS", {
        "anchor_height": anchor["anchor_height"], "anchor_hash": anchor["anchor_hash"],
        "tip_height": tip[0], "tip_hash": tip[1],
        "blocks": [item(block) for block in blocks], "more": more,
    }, request["request_id"])


def test_offline_node_catches_up_multiple_batches_and_parent_child_pages(tmp_path):
    async def scenario():
        a, b = Node(config(tmp_path / "a.sqlite3")), Node(config(tmp_path / "b.sqlite3"))
        reopened = None
        try:
            await a.start()
            await b.start()
            funding = await mine(a)
            await b.connect(*a.endpoint)
            await wait_status(b, lambda s: s["height"] == 1)
            await b.stop()
            for _ in range(5):
                await mine(a, MINER)
            parent = transfer(funding.transactions[0])
            child = transfer(parent, KEYS[1], [(40, CAROL)])
            assert await a.submit_transaction(parent)
            assert await a.submit_transaction(child)
            reopened = Node(config(tmp_path / "b.sqlite3", seeds=(a.endpoint,)))
            await reopened.start()
            await wait_status(reopened, lambda s: s["height"] == 6 and s["pending_count"] == 2)
            assert await reopened.get_pending_transactions() == [parent, child]
            assert await reopened.get_balance(ALICE) == 50
            assert (await reopened.get_status())["tip_hash"] == (await a.get_status())["tip_hash"]
            assert await reopened.validate_chain()
            assert reopened._chain._revision == a._chain._revision == 8
        finally:
            await close_nodes(a, b, *([reopened] if reopened else []))
    asyncio.run(scenario())


@pytest.mark.parametrize("remote_blocks", [1, 3])
def test_divergent_forks_are_reported_without_replacing_local_chain(tmp_path, remote_blocks):
    async def scenario():
        a, b = Node(config(tmp_path / "a.sqlite3")), Node(config(tmp_path / "b.sqlite3"))
        try:
            await a.start()
            await b.start()
            local = await mine(a, ALICE)
            for _ in range(remote_blocks):
                await mine(b, MINER)
            await a.connect(*b.endpoint)
            status = await wait_status(a, lambda s: any(
                p.get("sync_state") == "DIVERGED" and p.get("error") == "FORK_UNSUPPORTED"
                for p in s["peers"]
            ))
            assert status["height"] == 1 and status["tip_hash"] == local.hash()
            assert await a.get_balance(ALICE) == 50
            assert await a.get_balance(MINER) == 0
            assert await a.validate_chain() and await b.validate_chain()
            assert a._chain._revision == 1
        finally:
            await close_nodes(a, b)
        with Blockchain(db_path=tmp_path / "a.sqlite3") as chain:
            assert chain.height == 1 and chain.get_latest_block().hash() == local.hash()
    asyncio.run(scenario())


def test_valid_prefix_is_durable_when_next_downloaded_block_has_bad_pow(tmp_path):
    blocks = chain_blocks(3)
    invalid = deepcopy(blocks[1])
    while validate_proof_of_work(invalid):
        invalid.nonce += 1

    async def scenario():
        node = Node(config(tmp_path / "prefix.sqlite3"))
        peer = None
        try:
            await node.start()
            peer = await WirePeer.connect(node, height=3, tip_hash=blocks[-1].hash())
            request = await peer.receive("GET_BLOCKS")
            await respond_blocks(peer, request, [blocks[0], invalid],
                                 (3, blocks[-1].hash()), more=True)
            await wait_status(node, lambda s: s["height"] == 1)
            assert node.state == "RUNNING"
            assert await node.get_balance(ALICE) == 50
        finally:
            if peer:
                await peer.close()
            await node.stop()
    asyncio.run(scenario())
    with Blockchain(db_path=tmp_path / "prefix.sqlite3") as chain:
        assert chain.height == 1 and chain.get_latest_block().hash() == blocks[0].hash()
        assert chain.validate_chain()


def test_in_flight_response_is_stale_when_local_tip_advances():
    blocks = chain_blocks(2)

    async def scenario():
        node = Node(config())
        peer = None
        try:
            await node.start()
            peer = await WirePeer.connect(node, height=2, tip_hash=blocks[1].hash())
            old_request = await peer.receive("GET_BLOCKS")
            assert old_request["payload"]["anchor_height"] == 0
            assert await node.accept_block(blocks[0])
            await respond_blocks(peer, old_request, blocks, (2, blocks[1].hash()))
            assert (await peer.barrier())["height"] == 1
            fresh_request = await peer.receive("GET_BLOCKS")
            assert fresh_request["payload"]["anchor_height"] == 1
            assert fresh_request["payload"]["anchor_hash"] == blocks[0].hash()
            await respond_blocks(peer, fresh_request, [blocks[1]], (2, blocks[1].hash()))
            await wait_status(node, lambda s: s["height"] == 2)
            assert node.state == "RUNNING" and await node.validate_chain()
        finally:
            if peer:
                await peer.close()
            await node.stop()
    asyncio.run(scenario())


def test_unsolicited_blocks_cannot_change_state_and_only_close_offender():
    async def scenario():
        node = Node(config())
        peer = None
        try:
            await node.start()
            peer = await WirePeer.connect(node)
            await peer.send("BLOCKS", {
                "anchor_height": 0, "anchor_hash": GENESIS_HASH,
                "tip_height": 0, "tip_hash": GENESIS_HASH,
                "blocks": [], "more": False,
            }, secrets.token_hex(16))
            await wait_status(node, lambda s: len(s["peers"]) == 0)
            assert (await node.get_status())["height"] == 0
            assert node.state == "RUNNING"
        finally:
            if peer:
                await peer.close()
            await node.stop()
    asyncio.run(scenario())


def test_mempool_exchange_respects_receiver_capacity_without_failing_node():
    async def scenario():
        a, b = Node(config()), Node(config(mempool_max_transactions=1))
        try:
            await a.start()
            await b.start()
            funding = await mine(a)
            parent = transfer(funding.transactions[0])
            child = transfer(parent, KEYS[1], [(40, CAROL)])
            assert await a.submit_transaction(parent)
            assert await a.submit_transaction(child)
            await b.connect(*a.endpoint)
            await wait_status(b, lambda s: s["height"] == 1 and s["pending_count"] == 1)
            assert await b.get_pending_transactions() == [parent]
            assert await a.get_pending_transactions() == [parent, child]
            assert b.state == "RUNNING" and await b.validate_chain()
        finally:
            await close_nodes(a, b)
    asyncio.run(scenario())


@pytest.mark.parametrize("limit", ["count", "item"])
def test_mempool_snapshot_limits_report_policy_and_release_reservations(monkeypatch, limit):
    async def scenario():
        limits = {"snapshot_max_transactions": 1} if limit == "count" else {"max_item_bytes": 64}
        node = Node(config(**limits))
        peer = None
        try:
            await node.start()
            funding = await mine(node)
            parent = transfer(funding.transactions[0])
            child = transfer(parent, KEYS[1], [(40, CAROL)])
            assert await node.submit_transaction(parent)
            assert await node.submit_transaction(child)
            peer = await WirePeer.connect(node, height=1, tip_hash=funding.hash())
            request_id = secrets.token_hex(16)
            with monkeypatch.context() as patch:
                if limit == "count":
                    def forbidden_copy(self):
                        raise AssertionError("over-limit pool was copied before snapshot preflight")
                    patch.setattr("transaction.mempool.Mempool.copy", forbidden_copy)
                await peer.send("GET_MEMPOOL", {
                    "tip_hash": funding.hash(), "snapshot_id": None, "cursor": 0, "limit": 1,
                }, request_id)
                response = await peer.receive("ERROR", request_id=request_id)
                assert response["payload"]["code"] == "POLICY_LIMIT"
            assert node._sync.snapshot_bytes == 0
            assert await node.get_pending_transactions() == [parent, child]
            assert node.state == "RUNNING"
        finally:
            if peer:
                await peer.close()
            await node.stop()
    asyncio.run(scenario())


@pytest.mark.parametrize("invalidation", ["expiry", "tip"])
def test_mempool_snapshot_expiry_and_changed_tip_do_not_reuse_old_cursor(invalidation):
    async def scenario():
        node = Node(config(snapshot_idle_timeout=0.05))
        peer = None
        try:
            await node.start()
            funding = await mine(node)
            parent = transfer(funding.transactions[0])
            child = transfer(parent, KEYS[1], [(40, CAROL)])
            assert await node.submit_transaction(parent)
            assert await node.submit_transaction(child)
            peer = await WirePeer.connect(node, height=1, tip_hash=funding.hash())
            first_id = secrets.token_hex(16)
            await peer.send("GET_MEMPOOL", {
                "tip_hash": funding.hash(), "snapshot_id": None, "cursor": 0, "limit": 1,
            }, first_id)
            first = (await peer.receive("MEMPOOL", request_id=first_id))["payload"]
            assert first["transactions"] == [item(parent)] and not first["done"]
            assert first["next_cursor"] == 1
            if invalidation == "expiry":
                await wait_until(lambda: not node._sync.exports)
                expected = "SNAPSHOT_EXPIRED"
            else:
                await mine(node, MINER, max_transactions=1)
                expected = "STALE_TIP"
            next_id = secrets.token_hex(16)
            await peer.send("GET_MEMPOOL", {
                "tip_hash": funding.hash(), "snapshot_id": first["snapshot_id"],
                "cursor": first["next_cursor"], "limit": 1,
            }, next_id)
            response = await peer.receive("ERROR", request_id=next_id)
            assert response["payload"]["code"] == expected
            assert node._sync.snapshot_bytes == 0
            assert node.state == "RUNNING"
        finally:
            if peer:
                await peer.close()
            await node.stop()
    asyncio.run(scenario())


@pytest.mark.parametrize("failure", ["timeout", "no_progress"])
def test_false_height_source_yields_and_late_reply_is_ignored(failure):
    async def scenario():
        target = Node(config(request_timeout=0.08, retry_delay=0.15,
                             maintenance_interval=0.01))
        source = Node(config())
        liar = None
        try:
            await target.start()
            await source.start()
            blocks = [await mine(source), await mine(source)]
            liar = await WirePeer.connect(target, height=999, tip_hash="f" * 64)
            expired = await liar.receive("GET_BLOCKS")
            await target.connect(*source.endpoint)
            if failure == "no_progress":
                await respond_blocks(liar, expired, [], (0, GENESIS_HASH))
            await wait_status(target, lambda s: s["height"] == 2)
            # Even valid blocks cannot revive a request owned by an expired
            # download; the already verified chain remains the only state.
            if failure == "timeout":
                await respond_blocks(liar, expired, blocks, (2, blocks[-1].hash()))
            assert (await liar.barrier())["height"] == 2
            assert (await target.get_status())["tip_hash"] == blocks[-1].hash()
            assert await target.get_balance(ALICE) == 100
            assert target.state == "RUNNING" and await target.validate_chain()
        finally:
            if liar:
                await liar.close()
            await close_nodes(target, source)
    asyncio.run(scenario())


def test_response_from_wrong_connection_cannot_use_another_peers_request_id():
    blocks = chain_blocks(2)

    async def scenario():
        node = Node(config())
        source, attacker = None, None
        try:
            await node.start()
            source = await WirePeer.connect(node, height=2, tip_hash=blocks[-1].hash())
            request = await source.receive("GET_BLOCKS")
            attacker = await WirePeer.connect(node)
            await respond_blocks(attacker, request, blocks, (2, blocks[-1].hash()))
            await wait_status(node, lambda s: all(
                p["node_id"] != attacker.node_id for p in s["peers"]
            ))
            assert (await node.get_status())["height"] == 0
            await respond_blocks(source, request, blocks, (2, blocks[-1].hash()))
            await wait_status(node, lambda s: s["height"] == 2)
            assert await node.validate_chain()
        finally:
            for peer in (source, attacker):
                if peer:
                    await peer.close()
            await node.stop()
    asyncio.run(scenario())


@pytest.mark.parametrize("limit", ["count", "bytes"])
def test_incoming_mempool_limit_covers_all_pages_and_keeps_accepted_prefix(limit):
    funding = chain_blocks(1)[0]
    parent = transfer(funding.transactions[0])
    child = transfer(parent, KEYS[1], [(40, CAROL)])

    async def scenario():
        limits = ({"snapshot_max_transactions": 1} if limit == "count" else
                  {"snapshot_max_bytes": len(encode_transaction(parent)) + 1})
        node = Node(config(**limits))
        peer = None
        try:
            await node.start()
            assert await node.accept_block(funding)
            peer = await WirePeer.connect(node, height=1, tip_hash=funding.hash())
            request = await peer.receive("GET_MEMPOOL")
            token = secrets.token_hex(16)
            await peer.send("MEMPOOL", {
                "tip_hash": funding.hash(), "snapshot_id": token,
                "cursor": 0, "transactions": [item(parent)], "next_cursor": 1, "done": False,
            }, request["request_id"])
            second = await peer.receive("GET_MEMPOOL")
            assert second["payload"]["snapshot_id"] == token
            assert second["payload"]["cursor"] == 1
            await peer.send("MEMPOOL", {
                "tip_hash": funding.hash(), "snapshot_id": token,
                "cursor": 1, "transactions": [item(child)], "next_cursor": 2, "done": True,
            }, second["request_id"])
            await wait_status(node, lambda s: len(s["peers"]) == 0)
            assert await node.get_pending_transactions() == [parent]
            assert node.state == "RUNNING"
        finally:
            if peer:
                await peer.close()
            await node.stop()
    asyncio.run(scenario())
