"""Ledger state for a validated prefix of the chain."""

from dataclasses import dataclass, field

from blockchain.block import Block
from mining.coinbase import validate_coinbase_transaction
from transaction.processing import apply_transactions
from transaction.utxo import UTXOSet


@dataclass
class ChainState:
    utxo_set: UTXOSet = field(default_factory=UTXOSet)
    seen_txids: set[str] = field(default_factory=set)


def apply_block_transactions(block: Block, state: ChainState) -> ChainState | None:
    """Process a structurally checked block on a copy of its parent's state.

    Coinbase outputs are added last, so they cannot fund this block's transfers.
    The caller must check the block header, Merkle root and PoW first.
    """
    try:
        coinbase = block.transactions[0]
        coinbase_txid = coinbase.txid()
        if coinbase_txid in state.seen_txids:
            return None

        result = apply_transactions(
            block.transactions[1:], state.utxo_set, state.seen_txids
        )
        if coinbase_txid in result.seen_txids:
            return None
        if not validate_coinbase_transaction(
            coinbase,
            block_timestamp=block.timestamp,
            total_fees=result.total_fees,
        ):
            return None

        result.utxo_set.add_transaction_outputs(coinbase)
        result.seen_txids.add(coinbase_txid)
        return ChainState(result.utxo_set, result.seen_txids)
    except (AttributeError, IndexError, KeyError, TypeError, ValueError, OverflowError):
        return None
