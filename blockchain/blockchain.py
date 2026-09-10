from copy import deepcopy
from pathlib import Path

from blockchain.block import Block
from blockchain.chainstate import ChainState
from blockchain.genesis import create_genesis_block
from blockchain.validation import (
    validate_and_apply_block,
    rebuild_chain_state,
)
from mining.block_template import create_block_template
from storage.chain_store import SQLiteChainStore
from storage.errors import (
    StorageClosedError,
    StorageCommitUncertainError,
    StorageError,
)
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
        db_path: str | Path | None = None,
        current_time: int | None = None,
        mempool_max_transactions: int | None = None,
        mempool_max_bytes: int | None = None,
    ) -> None:
        if current_time is not None and (
            type(current_time) is not int or current_time < 0
        ):
            raise ValueError("current_time must be a non-negative integer")
        self._store: SQLiteChainStore | None = None
        self._closed = False
        self._storage_failed = False
        self._revision = 0
        self._blocks: list[Block] = [create_genesis_block()]
        self._state = ChainState()
        # Validate configuration before any connection can create a file.
        self._mempool = Mempool(
            self._state.utxo_set,
            self._state.seen_txids,
            max_transactions=(
                DEFAULT_MEMPOOL_MAX_TRANSACTIONS
                if mempool_max_transactions is None else mempool_max_transactions
            ),
            max_bytes=(
                DEFAULT_MEMPOOL_MAX_BYTES
                if mempool_max_bytes is None else mempool_max_bytes
            ),
        )
        if db_path is not None:
            store = SQLiteChainStore(db_path)
            try:
                recovered = store.load_or_initialize(
                    current_time=current_time,
                    max_transactions=mempool_max_transactions,
                    max_bytes=mempool_max_bytes,
                )
            except BaseException as error:
                try:
                    store.close()
                except Exception as cleanup_error:
                    if hasattr(error, "add_note"):
                        error.add_note(f"Store cleanup also failed: {cleanup_error}")
                raise
            self._store = store
            self._blocks, self._state, self._mempool, self._revision = (
                recovered.blocks, recovered.state, recovered.mempool,
                recovered.revision,
            )

    def _ensure_usable(self) -> None:
        if self._closed:
            raise StorageClosedError("Blockchain is closed; open a new instance")
        if self._storage_failed:
            raise StorageError("Storage operation failed; close and reopen the blockchain")

    def close(self) -> None:
        """Release the persistent connection; every mutation was already saved."""
        if self._store is not None and not self._closed:
            try:
                self._store.close()
            finally:
                self._closed = True

    def __enter__(self) -> "Blockchain":
        self._ensure_usable()
        return self

    def __exit__(self, exc_type, exc_value, traceback) -> None:
        if exc_value is None:
            self.close()
        else:
            try:
                self.close()
            except Exception as cleanup_error:
                if hasattr(exc_value, "add_note"):
                    exc_value.add_note(f"Store cleanup also failed: {cleanup_error}")

    def _commit(
        self,
        blocks: list[Block],
        state: ChainState,
        mempool: Mempool,
        *,
        block: Block | None = None,
    ) -> None:
        """Persist a prepared transition before publishing any live references."""
        if self._store is None:
            self._blocks, self._state, self._mempool = blocks, state, mempool
            return
        try:
            expected = {
                "expected_height": len(self._blocks) - 1,
                "expected_tip_hash": self._blocks[-1].hash(),
                "expected_revision": self._revision,
            }
            if block is None:
                revision = self._store.replace_mempool(mempool, **expected)
            else:
                revision = self._store.append_block(block, state, mempool, **expected)
            self._blocks, self._state, self._mempool, self._revision = (
                blocks, state, mempool, revision
            )
        except BaseException as error:
            # The disk outcome may be uncertain, even if Python never published
            # the new references. Never continue serving a possibly stale node.
            self._storage_failed = True
            if isinstance(error, StorageError):
                raise
            if isinstance(error, Exception):
                raise StorageCommitUncertainError(
                    "Persistent transition interrupted; close and reopen to recover"
                ) from error
            raise

    def __len__(self) -> int:
        self._ensure_usable()
        return len(self._blocks)

    @property
    def height(self) -> int:
        self._ensure_usable()
        return len(self._blocks) - 1

    @property
    def chain(self) -> list[Block]:
        self._ensure_usable()
        return deepcopy(self._blocks)

    @property
    def utxo_set(self) -> UTXOSet:
        """An independent snapshot; mutating it never changes live balances."""
        self._ensure_usable()
        return self._state.utxo_set.copy()

    @property
    def mempool(self) -> Mempool:
        """An independent snapshot; use submit/remove methods for live changes."""
        self._ensure_usable()
        return self._mempool.copy()

    def get_mempool_stats(self) -> tuple[int, int]:
        """Return count and signed bytes without copying state or writing disk."""
        self._ensure_usable()
        return len(self._mempool), self._mempool.total_bytes

    def submit_transaction(self, transaction: Transaction) -> bool:
        """Admit a pending transaction without changing confirmed state."""
        self._ensure_usable()
        if self._store is None:
            return self._mempool.add_transaction(transaction)
        next_mempool = self._mempool.copy()
        if not next_mempool.add_transaction(transaction):
            return False
        self._commit(self._blocks, self._state, next_mempool)
        return True

    def remove_pending_transaction(self, txid: str) -> bool:
        """Remove a pending transaction and descendants that lose their inputs."""
        self._ensure_usable()
        if self._store is None:
            return self._mempool.remove_transaction(txid)
        next_mempool = self._mempool.copy()
        if not next_mempool.remove_transaction(txid):
            return False
        self._commit(self._blocks, self._state, next_mempool)
        return True

    def get_balance(self, address: str) -> int:
        self._ensure_usable()
        return self._state.utxo_set.get_balance(address)

    def get_utxos_for_address(self, address: str) -> dict[tuple[str, int], TxOutput]:
        self._ensure_usable()
        return self._state.utxo_set.get_utxos_for_address(address)

    def has_transaction(self, txid: str) -> bool:
        self._ensure_usable()
        return isinstance(txid, str) and txid in self._state.seen_txids

    def create_block_template(
        self,
        miner_address: str,
        *,
        transactions: list[Transaction] | None = None,
        timestamp: int | None = None,
    ) -> Block:
        self._ensure_usable()
        return create_block_template(
            self._blocks[-1],
            miner_address,
            transactions=transactions,
            timestamp=timestamp,
            utxo_set=self._state.utxo_set,
            seen_txids=self._state.seen_txids,
        )

    def get_latest_block(self) -> Block:
        self._ensure_usable()
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
        self._ensure_usable()
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
        self._ensure_usable()
        if type(height) is not int:
            return None

        if height < 0 or height >= len(self._blocks):
            return None

        return deepcopy(self._blocks[height])

    def get_block_by_hash(self, block_hash: str) -> Block | None:
        self._ensure_usable()
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
        self._ensure_usable()
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

        # Allocate all replacements before SQLite commit. Block + confirmed
        # caches + revalidated pending pool must share one durable transaction.
        next_blocks = [*self._blocks, candidate]
        self._commit(next_blocks, next_state, next_mempool, block=candidate)
        return True

    def validate_chain(
        self,
        *,
        current_time: int | None = None,
    ) -> bool:
        self._ensure_usable()
        rebuilt = rebuild_chain_state(
            self._blocks,
            current_time=current_time,
        )
        return (
            rebuilt is not None
            and rebuilt.seen_txids == self._state.seen_txids
            and rebuilt.utxo_set.to_dict() == self._state.utxo_set.to_dict()
        )
