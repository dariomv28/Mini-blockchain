from copy import deepcopy
import time

from blockchain.block import Block
from consensus.difficulty import expected_difficulty
from mining.coinbase import create_coinbase_transaction
from transaction.transaction import Transaction


def _resolve_timestamp(timestamp: int | None) -> int:
    if timestamp is None:
        return int(time.time())

    if type(timestamp) is not int or timestamp < 0:
        raise ValueError("timestamp must be a non-negative integer")

    return timestamp


def create_block_template(
    previous_block: Block,
    miner_address: str,
    *,
    transactions: list[Transaction] | None = None,
    timestamp: int | None = None,
) -> Block:
    """Create a candidate with coinbase first and a deterministic difficulty.

    The caller still has to mine the returned block, then submit it through
    ``Blockchain.add_block()`` for full validation.
    """
    if not isinstance(previous_block, Block):
        raise TypeError("previous_block must be a Block")

    if (
        type(previous_block.timestamp) is not int
        or previous_block.timestamp < 0
    ):
        raise ValueError("previous_block.timestamp must be a non-negative integer")

    block_timestamp = _resolve_timestamp(timestamp)

    if timestamp is None:
        block_timestamp = max(block_timestamp, previous_block.timestamp)

    if block_timestamp < previous_block.timestamp:
        raise ValueError("timestamp cannot be earlier than the previous block")

    if transactions is None:
        regular_transactions: list[Transaction] = []
    elif not isinstance(transactions, list):
        raise TypeError("transactions must be a list of Transaction objects")
    elif not all(isinstance(transaction, Transaction) for transaction in transactions):
        raise TypeError("transactions must be a list of Transaction objects")
    else:
        regular_transactions = deepcopy(transactions)

    if any(
        not isinstance(transaction.inputs, list)
        or not transaction.inputs
        for transaction in regular_transactions
    ):
        raise ValueError("regular transactions must contain at least one input")

    coinbase = create_coinbase_transaction(
        miner_address,
        timestamp=block_timestamp,
    )

    return Block(
        transactions=[coinbase, *regular_transactions],
        previous_block_hash=previous_block.hash(),
        timestamp=block_timestamp,
        difficulty=expected_difficulty(previous_block.difficulty),
        nonce=0,
    )
