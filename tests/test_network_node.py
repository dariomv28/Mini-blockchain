"""Public node admission and multi-node TCP propagation contracts."""

import asyncio
from copy import deepcopy

import pytest

from mining.coinbase import create_coinbase_transaction
from blockchain.genesis import GENESIS_TIMESTAMP
from network import Node
from network.errors import NodeBusyError, NodeClosedError
from network_worker import (
    ALICE, BOB, CAROL, KEYS, MINER, WirePeer, close_nodes, config,
    item, mine, transfer, wait_status,
)


def test_three_independent_nodes_gossip_once_and_keep_child_on_confirmation(tmp_path):
    async def scenario():
        nodes = [Node(config(tmp_path / f"{name}.sqlite3")) for name in "abc"]
        a, b, c = nodes
        try:
            for node in nodes:
                await node.start()
            await b.connect(*a.endpoint)
            await c.connect(*b.endpoint)
            await a.connect(*c.endpoint)
            for node in nodes:
                await wait_status(node, lambda s: len(s["peers"]) == 2)
            assert len({id(node._chain) for node in nodes}) == 3
            funding = await mine(a)
            for node in nodes:
                await wait_status(node, lambda s: s["height"] == 1)
            parent = transfer(funding.transactions[0])
            child = transfer(parent, KEYS[1], [(40, CAROL)])
            assert await a.submit_transaction(parent)
            assert await a.submit_transaction(child)
            for node in nodes:
                await wait_status(node, lambda s: s["pending_count"] == 2)
                assert await node.get_pending_transactions() == [parent, child]
                assert not await node.submit_transaction(parent)
                assert not await node.submit_transaction(child)
                assert not await node.accept_block(funding)
                assert node._chain._revision == 3
            await mine(a, MINER, max_transactions=1)
            for node in nodes:
                await wait_status(node, lambda s: s["height"] == 2)
                assert await node.get_pending_transactions() == [child]
                assert await node.get_balance(BOB) == 45
                assert node._chain._revision == 4
            await mine(a, MINER, max_transactions=1)
            for node in nodes:
                await wait_status(node, lambda s: s["height"] == 3)
                assert await node.get_pending_transactions() == []
                assert await node.get_balance(CAROL) == 40
                assert await node.validate_chain()
                assert node._chain._revision == 5
            assert len({(await node.get_status())["tip_hash"] for node in nodes}) == 1
        finally:
            await close_nodes(*nodes)
    asyncio.run(scenario())


def test_rejected_child_can_be_retried_and_getters_are_detached():
    async def scenario():
        node = Node(config())
        try:
            await node.start()
            funding = await mine(node)
            parent = transfer(funding.transactions[0])
            original = deepcopy(parent)
            child = transfer(parent, KEYS[1], [(40, CAROL)])
            assert not await node.submit_transaction(child)
            assert await node.submit_transaction(parent)
            parent.outputs[0].amount = 1
            assert await node.get_pending_transactions() == [original]
            assert await node.submit_transaction(child)
            snapshot = await node.get_pending_transactions()
            snapshot[0].inputs.clear()
            snapshot.clear()
            block_snapshot = await node.get_block_by_height(1)
            block_snapshot.transactions.clear()
            assert await node.get_pending_transactions() == [original, child]
            assert (await node.get_block_by_height(1)).hash() == funding.hash()
            assert await node.validate_chain()
        finally:
            await node.stop()
    asyncio.run(scenario())


@pytest.mark.parametrize("defect", ["signature", "owner", "coinbase", "conflict"])
def test_invalid_remote_transaction_is_not_relayed_or_fatal(defect):
    async def scenario():
        a, b = Node(config()), Node(config())
        peer = None
        try:
            await a.start()
            await b.start()
            await b.connect(*a.endpoint)
            funding = await mine(a)
            await wait_status(b, lambda s: s["height"] == 1)
            peer = await WirePeer.connect(a, height=1, tip_hash=funding.hash())
            valid = transfer(funding.transactions[0])
            bad = deepcopy(valid)
            if defect == "signature":
                bad.inputs[0].signature = "00" * 64
            elif defect == "owner":
                bad.sign_input(0, KEYS[2])
            elif defect == "coinbase":
                bad = create_coinbase_transaction(MINER, timestamp=GENESIS_TIMESTAMP + 10)
            else:
                assert await a.submit_transaction(valid)
                await wait_status(b, lambda s: s["pending_count"] == 1)
                bad = transfer(funding.transactions[0], outputs=[(44, CAROL)])
            await peer.send("NEW_TRANSACTION", {"transaction": item(bad)})
            assert (await peer.barrier())["height"] == 1
            expected = [valid] if defect == "conflict" else []
            assert await a.get_pending_transactions() == expected
            assert await b.get_pending_transactions() == expected
            assert a.state == b.state == "RUNNING"
            if defect != "conflict":
                await peer.send("NEW_TRANSACTION", {"transaction": item(valid)})
                await wait_status(b, lambda s: s["pending_count"] == 1)
                assert await b.get_pending_transactions() == [valid]
        finally:
            if peer:
                await peer.close()
            await close_nodes(a, b)
    asyncio.run(scenario())


def test_local_capacity_rejection_and_invalid_inputs_do_not_poison_node():
    async def scenario():
        node = Node(config(mempool_max_transactions=1))
        try:
            await node.start()
            funding = await mine(node)
            parent = transfer(funding.transactions[0])
            child = transfer(parent, KEYS[1], [(40, CAROL)])
            for invalid in (None, {}, "not a transaction", 3):
                assert not await node.submit_transaction(invalid)
                assert not await node.accept_block(invalid)
            assert await node.submit_transaction(parent)
            assert not await node.submit_transaction(child)
            assert await node.get_pending_transactions() == [parent]
            assert node.state == "RUNNING"
        finally:
            await node.stop()
    asyncio.run(scenario())


def test_lifecycle_guards_cancelled_callers_and_concurrent_stop_release_port():
    async def scenario():
        node = Node(config())
        with pytest.raises(NodeClosedError):
            await node.get_status()
        await node.start()
        endpoint = node.endpoint
        pending = asyncio.create_task(node.get_status())
        pending.cancel()
        with pytest.raises(asyncio.CancelledError):
            await pending
        first = asyncio.create_task(node.stop())
        second = asyncio.create_task(node.stop())
        await asyncio.sleep(0)
        first.cancel()
        await asyncio.gather(first, return_exceptions=True)
        await asyncio.wait_for(second, 5)
        await node.stop()
        with pytest.raises(NodeClosedError):
            await node.get_pending_transactions()
        with pytest.raises(NodeClosedError):
            await node.submit_transaction(None)
        server = await asyncio.start_server(lambda reader, writer: writer.close(), *endpoint)
        server.close()
        await server.wait_closed()
        assert node.state == "STOPPED"
    asyncio.run(scenario())


def test_cancel_before_dispatch_does_not_admit_and_releases_budget():
    async def scenario():
        node = Node(config())
        try:
            await node.start()
            funding = await mine(node)
            transaction = transfer(funding.transactions[0])
            call = asyncio.create_task(node.submit_transaction(transaction))
            # Run the caller through enqueue, then cancel it before the newly
            # awakened dispatcher can begin the synchronous mutation.
            asyncio.get_running_loop().call_soon(call.cancel)
            with pytest.raises(asyncio.CancelledError):
                await call
            assert await node.get_pending_transactions() == []
            assert await node.submit_transaction(transaction)
        finally:
            await node.stop()
        assert node._inbound_events == node._inbound_bytes == 0
    asyncio.run(scenario())


def test_local_command_cannot_bypass_inbound_byte_limit():
    async def scenario():
        node = Node(config(inbound_max_bytes=64))
        try:
            await node.start()
            template = await node.create_mempool_block_template(ALICE)
            with pytest.raises(NodeBusyError):
                await node.accept_block(template)
            assert (await node.get_status())["height"] == 0
            assert node.state == "RUNNING"
        finally:
            await node.stop()
        assert node._inbound_events == node._inbound_bytes == 0
    asyncio.run(scenario())
