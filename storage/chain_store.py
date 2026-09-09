"""Atomic persistence and independent recovery of the active chain and pool."""

from dataclasses import dataclass
import sqlite3
import time

from blockchain.block import Block
from blockchain.chainstate import ChainState
from blockchain.genesis import GENESIS_HASH, create_genesis_block
from blockchain.validation import MAX_FUTURE_BLOCK_TIME, rebuild_chain_state
from crypto.hash import serialize, sha256_hex
from storage import block_store, chainstate_store, database
from storage.errors import (
    StorageClosedError,
    StorageConfigurationError,
    StorageConflictError,
    StorageCorruptionError,
    StorageError,
)
from transaction.mempool import DEFAULT_MEMPOOL_MAX_BYTES, DEFAULT_MEMPOOL_MAX_TRANSACTIONS, Mempool


@dataclass
class StoredChain:
    blocks: list[Block]
    state: ChainState
    mempool: Mempool
    revision: int


class SQLiteChainStore:
    def __init__(self, path):
        self._path = database.validate_path(path)
        self._connection: sqlite3.Connection | None = None
        self._closed = False

    def _require_connection(self) -> sqlite3.Connection:
        if self._closed:
            raise StorageClosedError("SQLite store is closed; reopen the database")
        if self._connection is None:
            raise StorageError("SQLite store has not been loaded")
        return self._connection

    def load_or_initialize(self, *, current_time: int | None = None, max_transactions: int | None = None, max_bytes: int | None = None) -> StoredChain:
        if self._closed:
            raise StorageClosedError("SQLite store is closed; reopen the database")
        for name, value in (("max_transactions", max_transactions), ("max_bytes", max_bytes)):
            if value is not None and (type(value) is not int or value <= 0):
                raise ValueError(f"{name} must be a positive integer or None")
        if current_time is not None and (type(current_time) is not int or current_time < 0):
            raise ValueError("current_time must be a non-negative integer or None")
        now = int(time.time()) if current_time is None else current_time
        try:
            if self._connection is None:
                self._connection, created = database.open_database(self._path)
                if created:
                    self._initialize(
                        DEFAULT_MEMPOOL_MAX_TRANSACTIONS if max_transactions is None else max_transactions,
                        DEFAULT_MEMPOOL_MAX_BYTES if max_bytes is None else max_bytes,
                    )
            connection = self._require_connection()
            with database.transaction(connection):
                database.validate_schema(connection)
                metadata = chainstate_store.read_metadata(connection)
                database.check_integrity(connection)
                self._check_configuration(metadata, max_transactions, max_bytes)
                blocks = block_store.read_block_rows(connection)
                if blocks[0].hash() != GENESIS_HASH or metadata.height != len(blocks) - 1 or metadata.tip_hash != blocks[-1].hash():
                    raise StorageCorruptionError("Metadata does not match the stored chain")
                state = rebuild_chain_state(blocks, current_time=now)
                if state is None:
                    detail = " (future timestamp relative to current_time)" if any(block.timestamp > now + MAX_FUTURE_BLOCK_TIME for block in blocks[1:]) else ""
                    raise StorageCorruptionError("Stored chain fails full consensus replay" + detail)
                cached = chainstate_store.read_chainstate_rows(connection)
                if cached.seen_txids != state.seen_txids or cached.utxo_set.to_dict() != state.utxo_set.to_dict():
                    raise StorageCorruptionError("Cached chain state differs from full block replay")
                mempool = chainstate_store.read_mempool_rows(connection, state, metadata)
                recovered = StoredChain(blocks, state, mempool, metadata.revision)
            return recovered
        except BaseException as exc:
            try:
                self.close()
            except BaseException as cleanup_error:
                if hasattr(exc, "add_note"):
                    exc.add_note(f"SQLite store cleanup also failed: {cleanup_error!r}")
            if isinstance(exc, sqlite3.Error):
                raise database.sqlite_storage_error(exc, "Failed to read SQLite chain storage") from exc
            raise

    def _initialize(self, max_transactions: int, max_bytes: int) -> None:
        genesis_row = block_store.encode_block_row(0, create_genesis_block())
        metadata = chainstate_store.metadata_row(0, GENESIS_HASH, 0, max_transactions, max_bytes, sha256_hex(serialize([])))
        connection = self._require_connection()
        with database.transaction(connection, write=True):
            database.create_schema(connection)
            block_store.insert_block_row(connection, genesis_row)
            chainstate_store.insert_metadata(connection, metadata)

    @staticmethod
    def _check_configuration(metadata, max_transactions, max_bytes) -> None:
        if (max_transactions is not None and max_transactions != metadata.max_transactions) or (max_bytes is not None and max_bytes != metadata.max_bytes):
            raise StorageConfigurationError("Mempool limits differ from the persisted configuration; online resizing is not supported")

    def _check_expected(self, connection, *, expected_height, expected_tip_hash, expected_revision, next_mempool):
        metadata = chainstate_store.read_metadata(connection)
        latest = connection.execute("SELECT height, hash FROM blocks ORDER BY height DESC LIMIT 1").fetchone()
        if (metadata.height, metadata.tip_hash, metadata.revision) != (expected_height, expected_tip_hash, expected_revision) or latest != (expected_height, expected_tip_hash):
            raise StorageConflictError("Database height, tip or revision changed; reopen before writing")
        self._check_configuration(metadata, next_mempool.max_transactions, next_mempool.max_bytes)

    def append_block(self, block: Block, next_state: ChainState, next_mempool: Mempool, *, expected_height: int, expected_tip_hash: str, expected_revision: int) -> int:
        connection = self._require_connection()
        next_height, next_revision = expected_height + 1, expected_revision + 1
        block_row = block_store.encode_block_row(next_height, block)
        state_rows = chainstate_store.encode_chainstate_rows(next_state)
        pool_rows = chainstate_store.encode_mempool_rows(next_mempool)
        mempool_digest = sha256_hex(serialize([row[1] for row in pool_rows]))
        chainstate_store.metadata_row(next_height, block_row[1], next_revision, next_mempool.max_transactions, next_mempool.max_bytes, mempool_digest)
        with database.transaction(connection, write=True):
            self._check_expected(connection, expected_height=expected_height, expected_tip_hash=expected_tip_hash, expected_revision=expected_revision, next_mempool=next_mempool)
            if block.previous_block_hash != expected_tip_hash:
                raise StorageConflictError("Candidate does not extend the expected stored tip")
            block_store.insert_block_row(connection, block_row)
            chainstate_store.replace_chainstate_rows(connection, state_rows)
            chainstate_store.replace_mempool_rows(connection, pool_rows)
            chainstate_store.update_metadata(connection, height=next_height, tip_hash=block_row[1], revision=next_revision, mempool_digest=mempool_digest, expected_height=expected_height, expected_tip_hash=expected_tip_hash, expected_revision=expected_revision)
        return next_revision

    def replace_mempool(self, next_mempool: Mempool, *, expected_height: int, expected_tip_hash: str, expected_revision: int) -> int:
        connection = self._require_connection()
        next_revision = expected_revision + 1
        pool_rows = chainstate_store.encode_mempool_rows(next_mempool)
        mempool_digest = sha256_hex(serialize([row[1] for row in pool_rows]))
        chainstate_store.metadata_row(expected_height, expected_tip_hash, next_revision, next_mempool.max_transactions, next_mempool.max_bytes, mempool_digest)
        with database.transaction(connection, write=True):
            self._check_expected(connection, expected_height=expected_height, expected_tip_hash=expected_tip_hash, expected_revision=expected_revision, next_mempool=next_mempool)
            chainstate_store.replace_mempool_rows(connection, pool_rows)
            chainstate_store.update_metadata(connection, height=expected_height, tip_hash=expected_tip_hash, revision=next_revision, mempool_digest=mempool_digest, expected_height=expected_height, expected_tip_hash=expected_tip_hash, expected_revision=expected_revision)
        return next_revision

    def close(self) -> None:
        if self._closed:
            return
        self._closed = True
        connection, self._connection = self._connection, None
        if connection is not None:
            try:
                connection.close()
            except sqlite3.Error as exc:
                raise StorageError("Could not close SQLite chain storage") from exc
