"""Persistence failures must never be confused with untrusted wire payloads."""

import asyncio
import base64
import json
from pathlib import Path
import subprocess
import sys

import pytest

from blockchain.blockchain import Blockchain
from network import Node
from network.errors import NodeClosedError
from network_worker import (
    ALICE, CAROL, KEYS, WirePeer, close_nodes, config, mine, transfer,
    wait_status, wait_until,
)
from storage.errors import StorageConflictError, StorageError


def test_restart_restores_pending_order_limits_and_exports_to_new_peer(tmp_path):
    async def scenario():
        path = tmp_path / "restored.sqlite3"
        first = Node(config(path, mempool_max_transactions=7))
        reopened, receiver = None, None
        try:
            await first.start()
            funding = await mine(first)
            parent = transfer(funding.transactions[0])
            child = transfer(parent, KEYS[1], [(40, CAROL)])
            assert await first.submit_transaction(parent)
            assert await first.submit_transaction(child)
            await first.stop()
            reopened = Node(config(path))
            await reopened.start()
            assert await reopened.get_pending_transactions() == [parent, child]
            assert reopened._chain.mempool.max_transactions == 7
            receiver = Node(config(tmp_path / "receiver.sqlite3", seeds=(reopened.endpoint,)))
            await receiver.start()
            await wait_status(receiver, lambda s: s["height"] == 1 and s["pending_count"] == 2)
            assert await receiver.get_pending_transactions() == [parent, child]
            assert await receiver.validate_chain()
            await receiver.stop()
            with Blockchain(db_path=tmp_path / "receiver.sqlite3") as chain:
                assert chain.mempool.get_transactions() == [parent, child]
                assert chain.get_balance(ALICE) == 50
        finally:
            await close_nodes(first, *[node for node in (reopened, receiver) if node])
    asyncio.run(scenario())


@pytest.mark.parametrize("committed", [False, True])
@pytest.mark.parametrize("operation", ["transaction", "block"])
def test_storage_fault_before_or_after_commit_fails_without_relay(
    tmp_path, monkeypatch, committed, operation,
):
    async def scenario():
        path = tmp_path / "fault.sqlite3"
        a, b = Node(config(path)), Node(config(tmp_path / "peer.sqlite3"))
        try:
            await a.start()
            await b.start()
            await b.connect(*a.endpoint)
            funding = await mine(a)
            await wait_status(b, lambda s: s["height"] == 1)
            transaction = transfer(funding.transactions[0])
            if operation == "transaction":
                method = "replace_mempool"
                mutate = lambda: a.submit_transaction(transaction)
            else:
                from mining.miner import mine_block
                method = "append_block"
                template = await a.create_mempool_block_template(ALICE)
                candidate = mine_block(template, max_nonce=100_000)
                assert candidate is not None
                mutate = lambda: a.accept_block(candidate)
            store = a._chain._store
            original = getattr(store, method)
            calls = []

            def fail(*args, **kwargs):
                calls.append(operation)
                if committed:
                    original(*args, **kwargs)
                raise StorageError("test-only injected local disk failure")

            monkeypatch.setattr(store, method, fail)
            with pytest.raises(StorageError, match="test-only"):
                await mutate()
            await wait_until(lambda: a.state == "FAILED")
            await a.stop()
            assert calls == [operation]
            with pytest.raises(NodeClosedError):
                await a.get_pending_transactions()
            assert (await b.get_status())["height"] == 1
            assert await b.get_pending_transactions() == []
            assert b.state == "RUNNING"
        finally:
            await close_nodes(a, b)
        with Blockchain(db_path=path) as recovered:
            assert recovered.height == (2 if committed and operation == "block" else 1)
            assert recovered.mempool.get_transactions() == (
                [transaction] if committed and operation == "transaction" else []
            )
            assert recovered.validate_chain()
    asyncio.run(scenario())


def test_stale_writer_stops_node_and_preserves_other_writers_pending(tmp_path):
    async def scenario():
        path = tmp_path / "shared-test-only.sqlite3"
        node = Node(config(path))
        try:
            await node.start()
            funding = await mine(node)
            external = transfer(funding.transactions[0])
            attempted = transfer(funding.transactions[0], outputs=[(44, CAROL)])
            with Blockchain(db_path=path) as other_writer:
                assert other_writer.submit_transaction(external)
            with pytest.raises(StorageConflictError):
                await node.submit_transaction(attempted)
            await wait_until(lambda: node.state == "FAILED")
        finally:
            await node.stop()
        with Blockchain(db_path=path) as chain:
            assert chain.mempool.get_transactions() == [external]
            assert chain.height == 1 and chain.validate_chain()
    asyncio.run(scenario())


def test_remote_codec_corruption_only_closes_offender(tmp_path):
    async def scenario():
        node = Node(config(tmp_path / "healthy.sqlite3"))
        peer = None
        try:
            await node.start()
            peer = await WirePeer.connect(node)
            # Valid canonical envelope/base64, malformed signed storage payload.
            await peer.send("NEW_TRANSACTION", {
                "transaction": base64.b64encode(b"{}").decode("ascii"),
            })
            await wait_status(node, lambda s: len(s["peers"]) == 0)
            assert node.state == "RUNNING"
            await mine(node)
            assert await node.validate_chain()
        finally:
            if peer:
                await peer.close()
            await node.stop()
        with Blockchain(db_path=tmp_path / "healthy.sqlite3") as chain:
            assert chain.height == 1 and chain.validate_chain()
    asyncio.run(scenario())


def test_startup_corrupt_database_is_preserved_without_ram_fallback(tmp_path):
    path = tmp_path / "corrupt.sqlite3"
    original = b"This is a deliberately malformed test database."
    path.write_bytes(original)

    async def scenario():
        node = Node(config(path))
        try:
            with pytest.raises(StorageError):
                await node.start()
            assert node.state == "FAILED"
            with pytest.raises(NodeClosedError):
                await node.get_status()
        finally:
            await node.stop()
        assert path.read_bytes() == original
    asyncio.run(scenario())


def test_independent_subprocess_syncs_and_persists_over_tcp(tmp_path):
    async def scenario():
        node = Node(config(tmp_path / "parent.sqlite3"))
        process = None
        try:
            await node.start()
            funding = await mine(node)
            pending = transfer(funding.transactions[0])
            assert await node.submit_transaction(pending)
            worker = Path(__file__).with_name("network_worker.py")
            process = await asyncio.create_subprocess_exec(
                sys.executable, "-B", str(worker),
                "--db", str(tmp_path / "child.sqlite3"),
                "--seed-port", str(node.endpoint[1]), "--height", "1", "--pending", "1",
                cwd=Path(__file__).resolve().parents[1],
                stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
            )
            stdout, stderr = await asyncio.wait_for(process.communicate(), timeout=25)
            assert process.returncode == 0, stderr.decode("utf-8", errors="replace")
            result = json.loads(stdout.decode("utf-8"))
            assert result["height"] == 1 and result["pending_count"] == 1
            assert result["tip_hash"] == funding.hash() and result["valid"]
            assert result["balance"] == 50
        finally:
            if process is not None and process.returncode is None:
                process.kill()
                await asyncio.wait_for(process.communicate(), timeout=5)
            await node.stop()
        with Blockchain(db_path=tmp_path / "child.sqlite3") as chain:
            assert chain.get_latest_block().hash() == funding.hash()
            assert chain.mempool.get_transactions() == [pending]
            assert chain.validate_chain()
    asyncio.run(scenario())
