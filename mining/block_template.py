from copy import deepcopy
import time

from blockchain.block import Block
from consensus.difficulty import expected_difficulty
from mining.coinbase import create_coinbase_transaction
from transaction.transaction import Transaction
from transaction.processing import apply_transactions
from transaction.utxo import UTXOSet


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
    utxo_set: UTXOSet | None = None,
    seen_txids: set[str] | None = None,
) -> Block:
    """Build a candidate using verified fees from the parent's ledger state.

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
        block_timestamp = max(block_timestamp, previous_block.timestamp + 1)

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

    if (utxo_set is None) != (seen_txids is None):
        raise ValueError("utxo_set and seen_txids must be supplied together")
    if regular_transactions and utxo_set is None:
        raise ValueError("Transactions require the parent UTXO and TXID state")

    total_fees = 0
    if utxo_set is not None:
        result = apply_transactions(regular_transactions, utxo_set, seen_txids)
        total_fees = result.total_fees

    coinbase = create_coinbase_transaction(
        miner_address,
        timestamp=block_timestamp,
        fees=total_fees,
    )
    if utxo_set is not None and coinbase.txid() in result.seen_txids:
        raise ValueError("Coinbase TXID already exists; choose a later timestamp")

    return Block(
        transactions=[coinbase, *regular_transactions],
        previous_block_hash=previous_block.hash(),
        timestamp=block_timestamp,
        difficulty=expected_difficulty(previous_block.difficulty),
        nonce=0,
    )
