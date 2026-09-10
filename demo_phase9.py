"""Three independent SQLite nodes: TCP gossip, restart and anchored catch-up."""

import asyncio
from pathlib import Path
from tempfile import TemporaryDirectory

from ecdsa import SECP256k1, SigningKey

from blockchain.genesis import GENESIS_TIMESTAMP
from crypto.address import public_key_to_address
from mining.miner import mine_block
from network import Node, NodeConfig
from transaction.transaction import Transaction
from transaction.tx_input import TxInput
from transaction.tx_output import TxOutput


def require(condition: bool, message: str) -> None:
    if not condition:
        raise RuntimeError(message)


async def wait_for(node: Node, *, height: int, pending: int) -> dict:
    deadline = asyncio.get_running_loop().time() + 15
    while True:
        status = await node.get_status()
        if status["height"] == height and status["pending_count"] == pending:
            return status
        if asyncio.get_running_loop().time() >= deadline:
            raise RuntimeError(f"Node did not converge: {status}")
        await asyncio.sleep(0.02)


async def mine(node: Node, address: str, *, max_transactions: int = 100):
    height = (await node.get_status())["height"]
    template = await node.create_mempool_block_template(
        address, timestamp=GENESIS_TIMESTAMP + height + 1,
        max_transactions=max_transactions,
    )
    # The miner only sees a detached template and a finite nonce range.
    mined = mine_block(template, max_nonce=100_000)
    require(mined is not None, "Demo nonce range exhausted")
    require(await node.accept_block(mined), "Mined block was rejected")
    return mined


async def describe(label: str, node: Node) -> None:
    status = await node.get_status()
    print(f"{label}: {node.endpoint[0]}:{node.endpoint[1]}, "
          f"peers={len(status['peers'])}, height={status['height']}, "
          f"tip={status['tip_hash'][:16]}, pending={status['pending_count']}")


async def scenario(directory: Path) -> None:
    # Fixed public educational keys; never use these for real funds.
    keys = [SigningKey.from_secret_exponent(n, curve=SECP256k1)
            for n in (401, 402, 403, 404)]
    alice, bob, carol, miner = addresses = [
        public_key_to_address(key.get_verifying_key()) for key in keys
    ]
    paths = [directory / f"node-{name}.sqlite3" for name in "abc"]
    nodes = []

    async def start(index: int) -> Node:
        node = Node(NodeConfig(db_path=paths[index], port=0,
                               block_batch_size=1, mempool_page_size=1))
        nodes.append(node)
        await node.start()
        return node

    try:
        a, b = await start(0), await start(1)
        await b.connect(*a.endpoint)
        funding = await mine(a, alice, max_transactions=0)
        await wait_for(b, height=1, pending=0)
        parent = Transaction(
            [TxInput(funding.transactions[0].txid(), 0)],
            [TxOutput(30, bob), TxOutput(18, alice)],
            timestamp=GENESIS_TIMESTAMP + 2,
        )
        parent.sign_input(0, keys[0])
        child = Transaction(
            [TxInput(parent.txid(), 0)], [TxOutput(27, carol)],
            timestamp=GENESIS_TIMESTAMP + 3,
        )
        child.sign_input(0, keys[1])
        require(await a.submit_transaction(parent), "Parent rejected")
        require(await a.submit_transaction(child), "Child rejected")
        await wait_for(b, height=1, pending=2)
        await describe("B before restart", b)

        await b.stop()
        b = await start(1)
        require(await b.get_pending_transactions() == [parent, child],
                "B did not restore signed parent/child order from its own DB")
        await describe("B restored before reconnect", b)
        await b.connect(*a.endpoint)

        c = await start(2)
        await c.connect(*b.endpoint)
        await wait_for(c, height=1, pending=2)
        require(await c.get_pending_transactions() == [parent, child],
                "C did not receive parent-first mempool pages")
        await describe("C after block batch and two mempool pages", c)
        await c.stop()

        await mine(a, miner, max_transactions=1)
        await wait_for(b, height=2, pending=1)
        require(await b.get_pending_transactions() == [child], "B lost the pending child")
        c = await start(2)
        await describe("C restored while one block behind", c)
        await c.connect(*b.endpoint)
        await wait_for(c, height=2, pending=1)
        require(await c.get_pending_transactions() == [child], "C lost the child after catch-up")
        await describe("C after reconnect catch-up batch", c)

        await mine(a, miner)
        for name, node in zip("ABC", (a, b, c)):
            await wait_for(node, height=3, pending=0)
            balances = [await node.get_balance(address) for address in addresses]
            require(balances == [18, 0, 27, 105], f"{name} has different balances")
            require(await node.validate_chain(), f"{name} chain failed full validation")
            await describe(f"{name} final; chain valid", node)
        tips = [(await node.get_status())["tip_hash"] for node in (a, b, c)]
        require(len(set(tips)) == 1, "Nodes ended at different tips")
        print("Confirmed balances (Alice, Bob, Carol, miner): 18 0 27 105")
        await asyncio.gather(a.stop(), b.stop(), c.stop())

        for index, name in enumerate("ABC"):
            reopened = await start(index)
            status = await reopened.get_status()
            require(status["height"] == 3 and status["tip_hash"] == tips[0]
                    and status["pending_count"] == 0, f"{name} restart lost state")
            require(await reopened.validate_chain(), f"{name} restart validation failed")
            await reopened.stop()
        print("All three independent databases reopened with the same validated state.")
    finally:
        await asyncio.gather(*(node.stop() for node in nodes))


def main() -> None:
    print("=== PHASE 9 - TCP NODES + SQLITE RESTART + SAME-BRANCH SYNC ===")
    with TemporaryDirectory(prefix="pychain-phase9-") as directory:
        asyncio.run(scenario(Path(directory)))
    print("Demo-owned databases cleaned up after all nodes and sockets closed.")


if __name__ == "__main__":
    main()
