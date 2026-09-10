"""Bounded TCP integration helpers and an independent process smoke worker."""

import argparse
import asyncio
import base64
import json
from pathlib import Path
import secrets
import struct
import sys

if __name__ == "__main__":
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from ecdsa import SECP256k1, SigningKey

from blockchain.genesis import GENESIS_HASH, GENESIS_TIMESTAMP
from crypto.address import public_key_to_address
from crypto.hash import serialize
from mining.miner import mine_block
from network import Node, NodeConfig
from storage.codec import encode_block, encode_transaction
from transaction.transaction import Transaction
from transaction.tx_input import TxInput
from transaction.tx_output import TxOutput


KEYS = [SigningKey.from_secret_exponent(n, curve=SECP256k1)
        for n in (411, 412, 413, 414)]
ALICE, BOB, CAROL, MINER = ADDRESSES = [
    public_key_to_address(key.get_verifying_key()) for key in KEYS
]


def config(db_path=None, **overrides):
    options = dict(db_path=db_path, port=0, block_batch_size=2,
                   mempool_page_size=1, request_timeout=1.0,
                   status_interval=0.2, mempool_refresh_interval=0.3,
                   retry_delay=0.1, maintenance_interval=0.02,
                   snapshot_cooldown=0.1)
    options.update(overrides)
    return NodeConfig(**options)


def transfer(source, key=KEYS[0], outputs=None, *, timestamp=GENESIS_TIMESTAMP + 10):
    transaction = Transaction(
        [TxInput(source.txid(), 0)],
        [TxOutput(amount, address) for amount, address in (outputs or [(45, BOB)])],
        timestamp=timestamp,
    )
    transaction.sign_input(0, key)
    return transaction


async def mine(node, address=ALICE, *, max_transactions=0):
    height = (await node.get_status())["height"]
    template = await node.create_mempool_block_template(
        address, timestamp=GENESIS_TIMESTAMP + height + 1,
        max_transactions=max_transactions,
    )
    block = mine_block(template, max_nonce=100_000)
    assert block is not None, "deterministic fixture exceeded its finite nonce range"
    assert await node.accept_block(block)
    return block


async def wait_status(node, predicate, *, timeout=8):
    deadline = asyncio.get_running_loop().time() + timeout
    while True:
        status = await node.get_status()
        if predicate(status):
            return status
        if asyncio.get_running_loop().time() >= deadline:
            raise AssertionError(f"node did not reach expected state: {status}")
        await asyncio.sleep(0.01)


async def wait_until(predicate, *, timeout=8):
    deadline = asyncio.get_running_loop().time() + timeout
    while not predicate():
        if asyncio.get_running_loop().time() >= deadline:
            raise AssertionError("condition did not become true before deadline")
        await asyncio.sleep(0.01)


async def close_nodes(*nodes):
    await asyncio.wait_for(asyncio.gather(*(node.stop() for node in nodes)), timeout=8)


def item(value):
    encoded = encode_transaction(value) if isinstance(value, Transaction) else encode_block(value)
    return base64.b64encode(encoded).decode("ascii")


class WirePeer:
    """Script a peer independently of the implementation's framing and schemas."""

    def __init__(self, reader, writer, *, height=0, tip_hash=GENESIS_HASH):
        self.reader, self.writer = reader, writer
        self.height, self.tip_hash = height, tip_hash
        self.node_id = secrets.token_hex(16)
        self.messages = []
        self.unhandled = []

    @classmethod
    async def connect(cls, node, **status):
        reader, writer = await asyncio.wait_for(asyncio.open_connection(*node.endpoint), 3)
        peer = cls(reader, writer, **status)
        version = await peer.read()
        assert version["type"] == "VERSION"
        await peer.send("VERSION", {
            "network_id": "mini-blockchain-v1", "genesis_hash": GENESIS_HASH,
            "node_id": peer.node_id, "connection_nonce": secrets.token_hex(16),
            "listen_port": writer.get_extra_info("sockname")[1],
            "height": peer.height, "tip_hash": peer.tip_hash,
        })
        await peer.send("VERACK", {})
        assert (await peer.read())["type"] == "VERACK"
        return peer

    async def send(self, kind, payload, request_id=None):
        body = serialize(dict(version=1, type=kind, request_id=request_id, payload=payload))
        self.writer.write(struct.pack(">I", len(body)) + body)
        await asyncio.wait_for(self.writer.drain(), 2)

    async def read(self, timeout=3):
        header = await asyncio.wait_for(self.reader.readexactly(4), timeout)
        size, = struct.unpack(">I", header)
        assert 1 <= size <= 4 * 1024 * 1024
        result = json.loads(await asyncio.wait_for(self.reader.readexactly(size), timeout))
        self.messages.append(result)
        return result

    async def receive(self, kind, *, request_id=None, timeout=3):
        for index, message in enumerate(self.unhandled):
            if message["type"] == kind and (request_id is None or message["request_id"] == request_id):
                return self.unhandled.pop(index)
        deadline = asyncio.get_running_loop().time() + timeout
        while True:
            message = await self.read(max(0.01, deadline - asyncio.get_running_loop().time()))
            if message["type"] == kind and (request_id is None or message["request_id"] == request_id):
                return message
            if message["type"] == "GET_STATUS":
                await self.send("STATUS", {"height": self.height, "tip_hash": self.tip_hash},
                                message["request_id"])
            elif message["type"] == "GET_PEERS":
                await self.send("PEERS", {"peers": []}, message["request_id"])
            elif message["type"] == "PING":
                await self.send("PONG", message["payload"])
            elif message["type"] == "GET_MEMPOOL":
                payload = message["payload"]
                await self.send("MEMPOOL", {
                    "tip_hash": self.tip_hash, "snapshot_id": secrets.token_hex(16),
                    "cursor": payload["cursor"], "transactions": [],
                    "next_cursor": payload["cursor"], "done": True,
                }, message["request_id"])
            else:
                self.unhandled.append(message)
            if asyncio.get_running_loop().time() >= deadline:
                raise AssertionError(f"peer never received {kind}")

    async def barrier(self):
        request_id = secrets.token_hex(16)
        await self.send("GET_STATUS", {}, request_id)
        return (await self.receive("STATUS", request_id=request_id))["payload"]

    async def close(self):
        self.writer.close()
        try:
            await asyncio.wait_for(self.writer.wait_closed(), 2)
        except (OSError, asyncio.TimeoutError):
            pass


async def _worker(args):
    node = Node(config(args.db, seeds=((args.seed_host, args.seed_port),)))
    try:
        await node.start()
        result = await wait_status(
            node, lambda status: status["height"] == args.height
            and status["pending_count"] == args.pending, timeout=15,
        )
        result["valid"] = await node.validate_chain()
        result["balance"] = await node.get_balance(ALICE)
        print(json.dumps(result), flush=True)
    finally:
        await node.stop()


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--db", required=True, type=Path)
    parser.add_argument("--seed-host", default="127.0.0.1")
    parser.add_argument("--seed-port", type=int, required=True)
    parser.add_argument("--height", type=int, required=True)
    parser.add_argument("--pending", type=int, required=True)
    asyncio.run(_worker(parser.parse_args()))
