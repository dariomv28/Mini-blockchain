"""SQLite connection policy, fixed schema and explicit transaction ownership."""

from contextlib import contextmanager
import os
from pathlib import Path
import re
import sqlite3

from storage.errors import (
    StorageCommitUncertainError,
    StorageCorruptionError,
    StorageError,
)


SCHEMA_VERSION = 1
MAX_SQLITE_INTEGER = 2**63 - 1
SCHEMA_SQL = {
    "blocks": """CREATE TABLE blocks (
        height INTEGER PRIMARY KEY CHECK (height >= 0),
        hash TEXT NOT NULL UNIQUE
            CHECK (length(hash) = 64 AND hash NOT GLOB '*[^0-9a-f]*'),
        previous_hash TEXT NOT NULL
            CHECK (length(previous_hash) = 64 AND previous_hash NOT GLOB '*[^0-9a-f]*'),
        data BLOB NOT NULL CHECK (typeof(data) = 'blob')
    )""",
    "seen_transactions": """CREATE TABLE seen_transactions (
        txid TEXT NOT NULL PRIMARY KEY
            CHECK (length(txid) = 64 AND txid NOT GLOB '*[^0-9a-f]*')
    )""",
    "utxos": """CREATE TABLE utxos (
        txid TEXT NOT NULL,
        output_index INTEGER NOT NULL
            CHECK (typeof(output_index) = 'integer' AND output_index >= 0),
        amount TEXT NOT NULL
            CHECK (typeof(amount) = 'text' AND length(amount) > 0
                   AND substr(amount, 1, 1) BETWEEN '1' AND '9'
                   AND amount NOT GLOB '*[^0-9]*'),
        recipient_address TEXT NOT NULL,
        PRIMARY KEY (txid, output_index),
        FOREIGN KEY (txid) REFERENCES seen_transactions(txid)
    )""",
    "mempool": """CREATE TABLE mempool (
        position INTEGER PRIMARY KEY CHECK (position >= 0),
        txid TEXT NOT NULL UNIQUE
            CHECK (length(txid) = 64 AND txid NOT GLOB '*[^0-9a-f]*'),
        data BLOB NOT NULL CHECK (typeof(data) = 'blob')
    )""",
    "metadata": """CREATE TABLE metadata (
        id INTEGER PRIMARY KEY CHECK (id = 1),
        schema_version INTEGER NOT NULL
            CHECK (typeof(schema_version) = 'integer' AND schema_version > 0),
        genesis_hash TEXT NOT NULL,
        tip_hash TEXT NOT NULL,
        height INTEGER NOT NULL
            CHECK (typeof(height) = 'integer' AND height >= 0),
        revision INTEGER NOT NULL
            CHECK (typeof(revision) = 'integer' AND revision >= 0),
        mempool_digest TEXT NOT NULL
            CHECK (length(mempool_digest) = 64 AND mempool_digest NOT GLOB '*[^0-9a-f]*'),
        mempool_max_transactions TEXT NOT NULL
            CHECK (typeof(mempool_max_transactions) = 'text'
                   AND length(mempool_max_transactions) > 0
                   AND substr(mempool_max_transactions, 1, 1) BETWEEN '1' AND '9'
                   AND mempool_max_transactions NOT GLOB '*[^0-9]*'),
        mempool_max_bytes TEXT NOT NULL
            CHECK (typeof(mempool_max_bytes) = 'text'
                   AND length(mempool_max_bytes) > 0
                   AND substr(mempool_max_bytes, 1, 1) BETWEEN '1' AND '9'
                   AND mempool_max_bytes NOT GLOB '*[^0-9]*'),
        FOREIGN KEY (tip_hash) REFERENCES blocks(hash)
    )""",
}
_AUTO_INDEXES = {
    "sqlite_autoindex_blocks_1": "blocks",
    "sqlite_autoindex_seen_transactions_1": "seen_transactions",
    "sqlite_autoindex_utxos_1": "utxos",
    "sqlite_autoindex_mempool_1": "mempool",
}


def sqlite_storage_error(exc: sqlite3.Error, message: str) -> StorageError:
    code = getattr(exc, "sqlite_errorcode", 0)
    if code & 255 in (sqlite3.SQLITE_CORRUPT, sqlite3.SQLITE_NOTADB):
        return StorageCorruptionError(message)
    return StorageError(message)


def validate_path(path: str | os.PathLike[str]) -> Path:
    try:
        raw = os.fspath(path)
    except TypeError as exc:
        raise TypeError("database path must be a string or PathLike") from exc
    if not isinstance(raw, str):
        raise TypeError("database path must be text, not bytes")
    if not raw.strip() or raw == ":memory:" or raw.lower().startswith("file:"):
        raise ValueError("database path must name a local SQLite file")
    if "\x00" in raw:
        raise ValueError("database path contains a null character")
    resolved = Path(raw).resolve()
    if resolved.exists() and not resolved.is_file():
        raise ValueError("database path must be a file, not a directory")
    if not resolved.parent.is_dir():
        raise ValueError("database parent directory must already exist")
    return resolved


def open_database(path: Path) -> tuple[sqlite3.Connection, bool]:
    """Exclusively create an absent file; never initialize an existing file."""
    connection = None
    try:
        try:
            descriptor = os.open(path, os.O_CREAT | os.O_EXCL | os.O_RDWR, 0o600)
        except FileExistsError:
            created = False
            if path.stat().st_size == 0:
                raise StorageCorruptionError("Existing database file is empty")
        else:
            os.close(descriptor)
            created = True

        options = {}
        if hasattr(sqlite3, "LEGACY_TRANSACTION_CONTROL"):
            options["autocommit"] = sqlite3.LEGACY_TRANSACTION_CONTROL
        # The internally constructed URI only selects rw mode: if an existing
        # file disappeared, sqlite must fail instead of silently recreating it.
        connection = sqlite3.connect(
            path.as_uri() + "?mode=rw",
            timeout=5.0,
            isolation_level=None,
            uri=True,
            **options,
        )
        connection.execute("PRAGMA foreign_keys = ON")
        connection.execute("PRAGMA synchronous = EXTRA")
        connection.execute("PRAGMA busy_timeout = 5000")
        mode = connection.execute(
            "PRAGMA journal_mode = DELETE" if created else "PRAGMA journal_mode"
        ).fetchone()[0]
        if str(mode).lower() != "delete":
            raise StorageError("Database journal_mode must already be DELETE")
        for pragma, expected in (("foreign_keys", 1), ("synchronous", 3), ("busy_timeout", 5000)):
            actual = connection.execute(f"PRAGMA {pragma}").fetchone()[0]
            if actual != expected:
                raise StorageError(f"SQLite could not apply {pragma}={expected}")
        return connection, created
    except BaseException as exc:
        if connection is not None:
            try:
                connection.close()
            except BaseException as cleanup_error:
                if hasattr(exc, "add_note"):
                    exc.add_note(f"SQLite connection cleanup also failed: {cleanup_error!r}")
        if isinstance(exc, sqlite3.DatabaseError):
            raise sqlite_storage_error(exc, "Cannot open/configure the SQLite database") from exc
        if isinstance(exc, OSError):
            raise StorageError("Cannot access the SQLite database file") from exc
        raise


def _normalize_ddl(statement: str) -> str:
    return re.sub(r"\s+", " ", statement).strip().rstrip(";")


def create_schema(connection: sqlite3.Connection) -> None:
    if connection.execute("SELECT name FROM sqlite_schema").fetchone() is not None:
        raise StorageCorruptionError("New database unexpectedly contains a schema")
    for statement in SCHEMA_SQL.values():
        connection.execute(statement)


def validate_schema(connection: sqlite3.Connection) -> None:
    expected_tables = set(SCHEMA_SQL)
    found_tables = set()
    found_indexes = set()
    for kind, name, table, statement in connection.execute(
        "SELECT type, name, tbl_name, sql FROM sqlite_schema"
    ).fetchall():
        if kind == "table" and name in expected_tables and table == name:
            if not isinstance(statement, str) or _normalize_ddl(statement) != _normalize_ddl(SCHEMA_SQL[name]):
                raise StorageCorruptionError(f"Unexpected schema definition for {name}")
            found_tables.add(name)
        elif kind == "index" and name in _AUTO_INDEXES and table == _AUTO_INDEXES[name] and statement is None:
            found_indexes.add(name)
        else:
            raise StorageCorruptionError(f"Unexpected schema object: {kind} {name}")
    if found_tables != expected_tables or found_indexes != set(_AUTO_INDEXES):
        raise StorageCorruptionError("Database schema is incomplete")


def check_integrity(connection: sqlite3.Connection) -> None:
    if connection.execute("PRAGMA integrity_check").fetchall() != [("ok",)]:
        raise StorageCorruptionError("SQLite integrity_check failed")
    if connection.execute("PRAGMA foreign_key_check").fetchone() is not None:
        raise StorageCorruptionError("SQLite foreign_key_check failed")


def commit_transaction(connection: sqlite3.Connection) -> None:
    """Single commit boundary, shared by initialization and subsequent writes."""
    connection.execute("COMMIT")


@contextmanager
def transaction(connection: sqlite3.Connection, *, write: bool = False):
    committing = False
    try:
        connection.execute("BEGIN IMMEDIATE" if write else "BEGIN")
        yield
        committing = True
        commit_transaction(connection)
    except BaseException as exc:
        try:
            if connection.in_transaction:
                connection.execute("ROLLBACK")
        except BaseException:
            # Preserve the operation/commit error, even if cleanup also fails.
            pass
        if committing and not isinstance(exc, StorageCommitUncertainError):
            raise StorageCommitUncertainError("SQLite COMMIT outcome is uncertain; reopen the database") from exc
        if isinstance(exc, sqlite3.Error):
            raise sqlite_storage_error(exc, "SQLite transaction failed") from exc
        if isinstance(exc, OverflowError):
            raise StorageError("SQLite integer storage bounds exceeded") from exc
        raise
