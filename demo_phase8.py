"""Persist signed pending transfers and a mined ledger across three restarts."""

from pathlib import Path
from tempfile import TemporaryDirectory

from ecdsa import SECP256k1, SigningKey

from blockchain.block import Block
from blockchain.blockchain import Blockchain
from blockchain.genesis import GENESIS_TIMESTAMP
from crypto.address import public_key_to_address
from mining.miner import mine_block
from transaction.transaction import Transaction
from transaction.tx_input import TxInput
from transaction.tx_output import TxOutput


def require(condition: bool, message: str) -> None:
    if not condition:
        raise RuntimeError(message)


def mine(template: Block) -> Block:
    result = mine_block(template, max_nonce=100_000)
    if result is None:
        raise RuntimeError("Demo nonce range exhausted")
    return result


def main() -> None:
    # Fixed public educational keys; never use them for real funds.
    keys = [SigningKey.from_secret_exponent(n, curve=SECP256k1)
            for n in (301, 302, 303, 304)]
    alice, bob, carol, miner = [
        public_key_to_address(key.get_verifying_key()) for key in keys
    ]
    now = GENESIS_TIMESTAMP + 100
    print("=== PHASE 8 - SQLITE + MEMPOOL PERSISTENCE ===")
    # Only this demo-owned directory is cleaned up, after connections close.
    with TemporaryDirectory(prefix="pychain-phase8-") as directory:
        path = Path(directory) / "chain.sqlite3"
        with Blockchain(db_path=path, current_time=now,
                        mempool_max_transactions=20) as chain:
            funding = mine(chain.create_block_template(
                alice, timestamp=GENESIS_TIMESTAMP + 1
            ))
            require(chain.add_block(funding, current_time=now), "Funding rejected")
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
            require(chain.submit_transaction(parent), "Parent rejected")
            require(chain.submit_transaction(child), "Child rejected")
            original_pool = chain.mempool.get_transactions()
            original_bytes = chain.mempool.total_bytes
            print("Pending before first close:", len(chain.mempool))
            print("Confirmed Alice balance:", chain.get_balance(alice))

        with Blockchain(db_path=path, current_time=now) as chain:
            restored = chain.mempool
            require(restored.get_transactions() == original_pool,
                    "Signed parent/child order was not restored")
            require(restored.total_bytes == original_bytes, "Pool bytes changed")
            require(restored.max_transactions == 20, "Saved limits were lost")
            print("Pending after first reopen:", len(restored))
            print("Restored mempool count limit:", restored.max_transactions)
            print("Revalidated parent/child fees:",
                  restored.get_entry(parent.txid()).fee,
                  restored.get_entry(child.txid()).fee)
            template = chain.create_mempool_block_template(
                miner, timestamp=GENESIS_TIMESTAMP + 2, max_transactions=1
            )
            require(template.transactions[1:] == [parent], "Parent must be ready first")
            require(chain.add_block(mine(template), current_time=now), "Parent block rejected")
            print("Pending after parent confirmation:", len(chain.mempool))

        with Blockchain(db_path=path, current_time=now) as chain:
            require(chain.mempool.get_transactions() == [child], "Child lost on restart")
            require(chain.has_transaction(parent.txid()), "Confirmed parent lost")
            print("Pending after second reopen:", len(chain.mempool))
            print("Bob confirmed balance:", chain.get_balance(bob))
            template = chain.create_mempool_block_template(
                miner, timestamp=GENESIS_TIMESTAMP + 3
            )
            require(chain.add_block(mine(template), current_time=now), "Child block rejected")

        with Blockchain(db_path=path, current_time=now) as chain:
            balances = [chain.get_balance(address)
                        for address in (alice, bob, carol, miner)]
            print("Final height:", chain.height)
            print("Final balances (Alice, Bob, Carol, miner):", *balances)
            print("Pending after third reopen:", len(chain.mempool))
            print("Chain valid:", chain.validate_chain(current_time=now))
            require(chain.height == 3 and balances == [18, 0, 27, 105],
                    "Recovered ledger differs from expected state")
            require(len(chain.mempool) == 0 and chain.has_transaction(child.txid()),
                    "Confirmed child was not persisted correctly")
            require(chain.validate_chain(current_time=now), "Full chain replay failed")
    print("Demo-owned temporary database cleaned up after all connections closed.")


if __name__ == "__main__":
    main()
