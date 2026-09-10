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
from network_worker import (
    ALICE, CAROL, KEYS, MINER, WirePeer, close_nodes, config, item,
    mine, transfer, wait_status,
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
