"""Sequential transaction processing on an isolated UTXO snapshot."""

from dataclasses import dataclass

from transaction.transaction import Transaction
from transaction.utxo import UTXOSet
from transaction.validation import calculate_transaction_fee


@dataclass
class TransactionBatch:
    utxo_set: UTXOSet
    seen_txids: set[str]
    total_fees: int


def apply_transactions(
    transactions: list[Transaction],
    utxo_set: UTXOSet,
    seen_txids: set[str],
) -> TransactionBatch:
    """Validate, calculate fees and apply in order; never mutate supplied state.

    Raises ValueError if any transaction is invalid or its TXID is repeated.
    Earlier outputs become available to later transactions in this batch.
    """
    if not isinstance(transactions, list):
        raise ValueError("transactions must be a list")
    if not isinstance(utxo_set, UTXOSet) or not isinstance(seen_txids, set):
        raise ValueError("a UTXO set and confirmed TXID set are required")

    working = utxo_set.copy()
    recorded = set(seen_txids)
    total_fees = 0

    for transaction in transactions:
        # calculate_transaction_fee validates the full transaction first.
        fee = calculate_transaction_fee(transaction, working)
        txid = transaction.txid()
        if txid in recorded:
            raise ValueError("Transaction ID has already been confirmed")
        try:
            working.apply_valid_transaction(transaction)
        except (KeyError, TypeError, ValueError) as error:
            raise ValueError("Transaction cannot be applied") from error
        recorded.add(txid)
        total_fees += fee

    return TransactionBatch(working, recorded, total_fees)
