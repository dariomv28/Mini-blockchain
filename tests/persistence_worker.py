"""Crash only the disposable test database at a real SQLite commit boundary."""

import os
from pathlib import Path
import sys


sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from blockchain.blockchain import Blockchain
from blockchain.genesis import GENESIS_TIMESTAMP
from crypto.address import public_key_to_address
from ecdsa import SECP256k1, SigningKey
from mining.miner import mine_block
from storage import database


def main():
    db_path, operation, crash_point = sys.argv[1:]
    chain = Blockchain(db_path=db_path, current_time=GENESIS_TIMESTAMP + 100)
    if operation == "append":
        miner = public_key_to_address(
            SigningKey.from_secret_exponent(34, curve=SECP256k1).get_verifying_key()
        )
        candidate = mine_block(
            chain.create_mempool_block_template(
                miner, timestamp=chain.get_latest_block().timestamp + 1
            ),
            max_nonce=100_000,
        )
        assert candidate is not None
        mutate = lambda: chain.add_block(candidate, current_time=GENESIS_TIMESTAMP + 100)
    elif operation == "remove":
        parent = chain.mempool.get_transactions()[0]
        mutate = lambda: chain.remove_pending_transaction(parent.txid())
    else:
        raise ValueError("unknown crash operation")

    original_commit = database.commit_transaction

    def crash_at_commit(connection):
        assert connection.in_transaction
        if crash_point == "before_commit":
            os._exit(71)
        if crash_point == "after_commit":
            original_commit(connection)
            assert not connection.in_transaction
            os._exit(72)
        raise ValueError("unknown crash point")

    database.commit_transaction = crash_at_commit
    mutate()
    raise AssertionError("operation never reached its durable commit boundary")


if __name__ == "__main__":
    main()
