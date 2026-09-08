from copy import deepcopy

from blockchain.block import Block
from blockchain.chainstate import ChainState
from blockchain.genesis import create_genesis_block
from blockchain.validation import (
    validate_and_apply_block,
    rebuild_chain_state,
)
from mining.block_template import create_block_template
from transaction.mempool import (
    DEFAULT_BLOCK_MAX_BYTES,
    DEFAULT_BLOCK_MAX_TRANSACTIONS,
    DEFAULT_MEMPOOL_MAX_BYTES,
    DEFAULT_MEMPOOL_MAX_TRANSACTIONS,
    Mempool,
)
from transaction.transaction import Transaction
from transaction.tx_output import TxOutput
from transaction.utxo import UTXOSet


class Blockchain:

    def __init__(
        self,
        *,
        mempool_max_transactions: int = DEFAULT_MEMPOOL_MAX_TRANSACTIONS,
        mempool_max_bytes: int = DEFAULT_MEMPOOL_MAX_BYTES,
    ) -> None:
        self._blocks: list[Block] = [create_genesis_block()]
        self._state = ChainState()
        self._mempool = Mempool(
            self._state.utxo_set,
            self._state.seen_txids,
            max_transactions=mempool_max_transactions,
            max_bytes=mempool_max_bytes,
        )

    def __len__(self) -> int:
        return len(self._blocks)

    @property
    def height(self) -> int:
        return len(self._blocks) - 1

    @property
    def chain(self) -> list[Block]:
        return deepcopy(self._blocks)

    @property
    def utxo_set(self) -> UTXOSet:
        """An independent snapshot; mutating it never changes live balances."""
        return self._state.utxo_set.copy()

    @property
    def mempool(self) -> Mempool:
        """An independent snapshot; use submit/remove methods for live changes."""
        return self._mempool.copy()

    def submit_transaction(self, transaction: Transaction) -> bool:
        """Admit a pending transaction without changing confirmed state."""
        return self._mempool.add_transaction(transaction)

    def remove_pending_transaction(self, txid: str) -> bool:
        """Remove a pending transaction and descendants that lose their inputs."""
        return self._mempool.remove_transaction(txid)

    def get_balance(self, address: str) -> int:
        return self._state.utxo_set.get_balance(address)

    def get_utxos_for_address(self, address: str) -> dict[tuple[str, int], TxOutput]:
        return self._state.utxo_set.get_utxos_for_address(address)

    def has_transaction(self, txid: str) -> bool:
        return isinstance(txid, str) and txid in self._state.seen_txids

    def create_block_template(
        self,
        miner_address: str,
        *,
        transactions: list[Transaction] | None = None,
        timestamp: int | None = None,
    ) -> Block:
        return create_block_template(
            self._blocks[-1],
            miner_address,
            transactions=transactions,
            timestamp=timestamp,
            utxo_set=self._state.utxo_set,
            seen_txids=self._state.seen_txids,
        )

    def get_latest_block(self) -> Block:
        return deepcopy(self._blocks[-1])

    def create_mempool_block_template(
        self,
        miner_address: str,
        *,
        timestamp: int | None = None,
        max_transactions: int = DEFAULT_BLOCK_MAX_TRANSACTIONS,
        max_bytes: int = DEFAULT_BLOCK_MAX_BYTES,
    ) -> Block:
        """Select pending transactions, then independently verify their fees.

        Limits cover regular transactions only, not coinbase or block framing.
        Building/mining a template does not remove transactions from the pool.
        """
        selected = self._mempool.select_transactions(
            max_transactions=max_transactions,
            max_bytes=max_bytes,
        )
        return self.create_block_template(
            miner_address,
            transactions=selected,
            timestamp=timestamp,
        )

    def get_block_by_height(self, height: int) -> Block | None:
        if type(height) is not int:
            return None

        if height < 0 or height >= len(self._blocks):
            return None

        return deepcopy(self._blocks[height])

    def get_block_by_hash(self, block_hash: str) -> Block | None:
        for block in self._blocks:
            if block.hash() == block_hash:
                return deepcopy(block)

        return None

    def add_block(
        self,
        block: Block,
        *,
        current_time: int | None = None,
    ) -> bool:
        if not isinstance(block, Block):
            return False

        candidate = deepcopy(block)

        next_state = validate_and_apply_block(
            candidate,
            self._blocks[-1],
            state=self._state,
            current_time=current_time,
        )
        if next_state is None:
            return False

        candidate_hash = candidate.hash()

        if any(
            existing.hash() == candidate_hash
            for existing in self._blocks
        ):
            return False

        # Pending reservations are local policy, not consensus. Revalidate
        # only after block validation, preserving children of confirmed parents.
        next_mempool = self._mempool.revalidated(
            next_state.utxo_set,
            next_state.seen_txids,
        )

        # Build every replacement first. A rejected block never changes history,
        # confirmed state or pool. This is a single-threaded in-memory commit.
        self._blocks, self._state, self._mempool = (
            [*self._blocks, candidate], next_state, next_mempool
        )
        return True

    def validate_chain(
        self,
        *,
        current_time: int | None = None,
    ) -> bool:
        rebuilt = rebuild_chain_state(
            self._blocks,
            current_time=current_time,
        )
        return (
            rebuilt is not None
            and rebuilt.seen_txids == self._state.seen_txids
            and rebuilt.utxo_set.to_dict() == self._state.utxo_set.to_dict()
        )
