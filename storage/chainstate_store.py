"""Map confirmed state, pending transactions and metadata to SQLite rows."""

from dataclasses import dataclass
import sqlite3

from blockchain.chainstate import ChainState
from blockchain.genesis import GENESIS_HASH
from crypto.address import validate_address
from crypto.hash import serialize, sha256_hex
from storage.codec import decode_amount, decode_transaction, encode_amount, encode_transaction
from storage.database import MAX_SQLITE_INTEGER, SCHEMA_VERSION
from storage.errors import StorageConflictError, StorageCorruptionError, StorageError, StorageVersionError
from transaction.mempool import Mempool
from transaction.tx_output import TxOutput
from transaction.utxo import UTXOSet


@dataclass(frozen=True)
class Metadata:
    height: int
    tip_hash: str
    revision: int
    max_transactions: int
    max_bytes: int
    mempool_digest: str


def _is_hash(value: object) -> bool:
    return isinstance(value, str) and len(value) == 64 and all(char in "0123456789abcdef" for char in value)


def encode_chainstate_rows(state: ChainState) -> tuple[list[tuple], list[tuple]]:
    if not isinstance(state, ChainState) or not isinstance(state.utxo_set, UTXOSet) or not isinstance(state.seen_txids, set):
        raise StorageError("Cannot encode malformed chain state")
    if not all(_is_hash(txid) for txid in state.seen_txids):
        raise StorageError("Chain state contains a malformed historical TXID")
    seen_rows = [(txid,) for txid in sorted(state.seen_txids)]
    utxo_rows = []
    for (txid, output_index), output in sorted(state.utxo_set.to_dict().items()):
        if txid not in state.seen_txids or type(output_index) is not int or not 0 <= output_index <= MAX_SQLITE_INTEGER:
            raise StorageError("UTXO outpoint cannot be stored")
        if not isinstance(output, TxOutput) or not validate_address(output.recipient_address):
            raise StorageError("UTXO recipient address is invalid")
        utxo_rows.append((txid, output_index, encode_amount(output.amount), output.recipient_address))
    return seen_rows, utxo_rows


def replace_chainstate_rows(connection: sqlite3.Connection, rows: tuple[list[tuple], list[tuple]]) -> None:
    seen_rows, utxo_rows = rows
    connection.execute("DELETE FROM utxos")
    connection.execute("DELETE FROM seen_transactions")
    connection.executemany("INSERT INTO seen_transactions(txid) VALUES (?)", seen_rows)
    connection.executemany(
        "INSERT INTO utxos(txid, output_index, amount, recipient_address) VALUES (?, ?, ?, ?)",
        utxo_rows,
    )


def read_chainstate_rows(connection: sqlite3.Connection) -> ChainState:
    seen_rows = connection.execute("SELECT txid FROM seen_transactions").fetchall()
    seen = set()
    for (txid,) in seen_rows:
        if not _is_hash(txid) or txid in seen:
            raise StorageCorruptionError("Malformed or duplicate historical TXID")
        seen.add(txid)
    utxos = UTXOSet()
    for txid, output_index, amount, address in connection.execute(
        "SELECT txid, output_index, amount, recipient_address FROM utxos"
    ).fetchall():
        if txid not in seen or type(output_index) is not int or output_index < 0:
            raise StorageCorruptionError("Malformed cached UTXO outpoint")
        if not validate_address(address):
            raise StorageCorruptionError("Malformed cached UTXO address")
        if utxos.exists(txid, output_index):
            raise StorageCorruptionError("Duplicate cached UTXO outpoint")
        utxos.add(txid, output_index, TxOutput(decode_amount(amount), address))
    return ChainState(utxos, seen)


def encode_mempool_rows(mempool: Mempool) -> list[tuple[int, str, bytes]]:
    if not isinstance(mempool, Mempool):
        raise StorageError("Cannot encode malformed mempool")
    rows = [(position, tx.txid(), encode_transaction(tx)) for position, tx in enumerate(mempool.get_transactions())]
    if len(rows) > mempool.max_transactions or sum(len(row[2]) for row in rows) > mempool.max_bytes:
        raise StorageError("Mempool exceeds its persisted capacity")
    return rows


def replace_mempool_rows(connection: sqlite3.Connection, rows: list[tuple[int, str, bytes]]) -> None:
    connection.execute("DELETE FROM mempool")
    connection.executemany("INSERT INTO mempool(position, txid, data) VALUES (?, ?, ?)", rows)


def read_mempool_rows(connection: sqlite3.Connection, state: ChainState, metadata: Metadata) -> Mempool:
    pool = Mempool(
        state.utxo_set,
        state.seen_txids,
        max_transactions=metadata.max_transactions,
        max_bytes=metadata.max_bytes,
    )
    for expected_position, (position, txid, data) in enumerate(connection.execute(
        "SELECT position, txid, data FROM mempool ORDER BY position"
    ).fetchall()):
        if type(position) is not int or position != expected_position:
            raise StorageCorruptionError("Mempool positions are not contiguous from zero")
        transaction = decode_transaction(data)
        if not _is_hash(txid) or txid != transaction.txid():
            raise StorageCorruptionError("Mempool TXID disagrees with its signed payload")
        if not pool.add_transaction(transaction):
            raise StorageCorruptionError("Persisted mempool contains an invalid, conflicting, orphan or over-capacity transaction")
    if sha256_hex(serialize([tx.txid() for tx in pool.get_transactions()])) != metadata.mempool_digest:
        raise StorageCorruptionError("Mempool contents/order differ from the committed digest")
    return pool


def metadata_row(height: int, tip_hash: str, revision: int, max_transactions: int, max_bytes: int, mempool_digest: str) -> tuple:
    for value in (height, revision):
        if type(value) is not int or not 0 <= value <= MAX_SQLITE_INTEGER:
            raise StorageError("Metadata height/revision exceeds SQLite integer storage bounds")
    if not _is_hash(tip_hash) or not _is_hash(mempool_digest):
        raise StorageError("Cannot store a malformed tip hash or mempool digest")
    return (1, SCHEMA_VERSION, GENESIS_HASH, tip_hash, height, revision, mempool_digest, encode_amount(max_transactions), encode_amount(max_bytes))


def insert_metadata(connection: sqlite3.Connection, row: tuple) -> None:
    connection.execute(
        "INSERT INTO metadata(id, schema_version, genesis_hash, tip_hash, height, revision, mempool_digest, mempool_max_transactions, mempool_max_bytes) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
        row,
    )


def read_metadata(connection: sqlite3.Connection) -> Metadata:
    rows = connection.execute(
        "SELECT id, schema_version, genesis_hash, tip_hash, height, revision, mempool_digest, mempool_max_transactions, mempool_max_bytes FROM metadata"
    ).fetchall()
    if len(rows) != 1:
        raise StorageCorruptionError("Metadata must contain exactly one singleton row")
    identity, version, genesis_hash, tip_hash, height, revision, mempool_digest, max_transactions, max_bytes = rows[0]
    if type(version) is not int or version <= 0:
        raise StorageCorruptionError("Malformed storage schema version")
    if version != SCHEMA_VERSION:
        raise StorageVersionError(f"Unsupported storage schema version: {version}")
    if identity != 1 or genesis_hash != GENESIS_HASH or not _is_hash(tip_hash) or not _is_hash(mempool_digest):
        raise StorageCorruptionError("Metadata identity, genesis or tip hash is invalid")
    if type(height) is not int or height < 0 or type(revision) is not int or revision < height:
        raise StorageCorruptionError("Metadata height/revision is invalid")
    return Metadata(height, tip_hash, revision, decode_amount(max_transactions), decode_amount(max_bytes), mempool_digest)


def update_metadata(connection: sqlite3.Connection, *, height: int, tip_hash: str, revision: int, mempool_digest: str, expected_height: int, expected_tip_hash: str, expected_revision: int) -> None:
    result = connection.execute(
        "UPDATE metadata SET height = ?, tip_hash = ?, revision = ?, mempool_digest = ? WHERE id = 1 AND height = ? AND tip_hash = ? AND revision = ?",
        (height, tip_hash, revision, mempool_digest, expected_height, expected_tip_hash, expected_revision),
    )
    if result.rowcount != 1:
        raise StorageConflictError("Database state changed; reopen before writing")
