from contextlib import closing
from copy import deepcopy
import sqlite3

import pytest
from ecdsa import SECP256k1, SigningKey

from blockchain.blockchain import Blockchain
from blockchain.chainstate import ChainState
from blockchain.genesis import GENESIS_HASH, GENESIS_TIMESTAMP
from blockchain.validation import rebuild_chain_state
from crypto.address import public_key_to_address
from crypto.hash import serialize, sha256_hex
from mining.miner import mine_block
from storage import block_store, chainstate_store, database
from storage.chain_store import SQLiteChainStore
from storage.codec import encode_block, encode_transaction
from storage.errors import (
    StorageClosedError,
    StorageCommitUncertainError,
    StorageConfigurationError,
    StorageConflictError,
    StorageCorruptionError,
    StorageError,
    StorageVersionError,
)
from transaction.mempool import Mempool
from transaction.transaction import Transaction
from transaction.tx_input import TxInput
from transaction.tx_output import TxOutput


NOW = GENESIS_TIMESTAMP + 100
KEY = SigningKey.from_secret_exponent(41, curve=SECP256k1)
ADDRESS = public_key_to_address(KEY.get_verifying_key())


def open_store(path, **kwargs):
    store = SQLiteChainStore(path)
    return store, store.load_or_initialize(current_time=NOW, **kwargs)


def edit(path, sql, parameters=()):
    with closing(sqlite3.connect(path)) as connection:
        connection.execute(sql, parameters)
        connection.commit()


def query(path, sql, parameters=()):
    with closing(sqlite3.connect(path)) as connection:
        return connection.execute(sql, parameters).fetchall()


def logical_snapshot(path):
    return {
        name: query(path, f"SELECT * FROM {name} ORDER BY 1")
        for name in database.SCHEMA_SQL
    }


def transfer(source, *, amount=45, output_index=0, timestamp=123):
    transaction = Transaction(
        [TxInput(source.txid(), output_index)],
        [TxOutput(amount, ADDRESS)],
        timestamp=timestamp,
    )
    transaction.sign_input(0, KEY)
    return transaction


def append_ram_tip(store, chain, revision):
    blocks = chain.chain
    state = rebuild_chain_state(blocks, current_time=NOW)
    assert state is not None
    return store.append_block(
        blocks[-1], state, chain.mempool,
        expected_height=len(blocks) - 2,
        expected_tip_hash=blocks[-2].hash(),
        expected_revision=revision,
    )


@pytest.fixture
def stored(tmp_path):
    path = tmp_path / "chain.sqlite"
    store, recovered = open_store(path)
    yield path, store, recovered
    store.close()


@pytest.fixture
def funded(stored):
    path, store, _ = stored
    chain = Blockchain()
    funding = mine_block(
        chain.create_block_template(ADDRESS, timestamp=GENESIS_TIMESTAMP + 1),
        max_nonce=100_000,
    )
    assert funding is not None
    assert chain.add_block(funding, current_time=NOW)
    assert append_ram_tip(store, chain, 0) == 1
    return path, store, chain, funding.transactions[0]


def save_pending(store, chain, revision):
    return store.replace_mempool(
        chain.mempool,
        expected_height=chain.height,
        expected_tip_hash=chain.get_latest_block().hash(),
        expected_revision=revision,
    )


def make_pending_family(funded):
    path, store, chain, funding = funded
    parent = transfer(funding)
    child = transfer(parent, amount=40)
    assert chain.submit_transaction(parent)
    assert chain.submit_transaction(child)
    assert save_pending(store, chain, 1) == 2
    return path, store, chain, parent, child


def assert_corrupt(path, *, match=None):
    with pytest.raises(StorageCorruptionError, match=match):
        open_store(path)


def test_new_database_initializes_exact_schema_genesis_and_settings(stored):
    path, store, recovered = stored
    assert len(recovered.blocks) == 1
    assert recovered.blocks[0].hash() == GENESIS_HASH
    assert recovered.revision == 0
    assert recovered.state.seen_txids == set()
    assert recovered.state.utxo_set.to_dict() == {}
    assert len(recovered.mempool) == 0
    assert set(logical_snapshot(path)) == {"blocks", "utxos", "seen_transactions", "mempool", "metadata"}
    assert query(path, "SELECT mempool_max_transactions, mempool_max_bytes FROM metadata") == [("1000", "1000000")]
    assert query(path, "SELECT mempool_digest FROM metadata") == [(sha256_hex(serialize([])),)]
    connection = store._connection
    assert connection.isolation_level is None
    if hasattr(sqlite3, "LEGACY_TRANSACTION_CONTROL"):
        assert connection.autocommit == sqlite3.LEGACY_TRANSACTION_CONTROL
    assert not connection.in_transaction
    for pragma, expected in (("journal_mode", "delete"), ("synchronous", 3), ("foreign_keys", 1), ("busy_timeout", 5000)):
        assert connection.execute(f"PRAGMA {pragma}").fetchone()[0] == expected


def test_reopen_preserves_every_confirmed_table_and_does_not_duplicate_genesis(funded):
    path, store, chain, funding = funded
    before = logical_snapshot(path)
    store.close()
    reopened, recovered = open_store(path)
    try:
        assert [block.to_dict() for block in recovered.blocks] == [block.to_dict() for block in chain.chain]
        assert recovered.state.utxo_set.to_dict() == chain.utxo_set.to_dict()
        assert recovered.state.seen_txids == {funding.txid()}
        assert recovered.revision == 1
        assert logical_snapshot(path) == before
    finally:
        reopened.close()


def test_pending_parent_child_round_trip_revalidates_fee_and_size(funded):
    path, store, chain, parent, child = make_pending_family(funded)
    store.close()
    reopened, recovered = open_store(path)
    try:
        assert recovered.mempool.get_transactions() == [parent, child]
        assert recovered.mempool.get_entry(parent.txid()).fee == 5
        assert recovered.mempool.get_entry(child.txid()).fee == 5
        assert recovered.mempool.total_bytes == sum(len(encode_transaction(tx)) for tx in [parent, child])
        assert recovered.state.utxo_set.to_dict() == chain.utxo_set.to_dict()
        assert recovered.revision == 2
    finally:
        reopened.close()


def test_large_transaction_timestamp_survives_pending_and_confirmed_restart(funded):
    path, store, chain, funding = funded
    transaction = transfer(funding, timestamp=2**80)
    assert chain.submit_transaction(transaction)
    assert save_pending(store, chain, 1) == 2
    store.close()
    reopened, recovered = open_store(path)
    try:
        assert recovered.mempool.get_transaction(transaction.txid()).timestamp == 2**80
        block = mine_block(
            chain.create_mempool_block_template(ADDRESS, timestamp=GENESIS_TIMESTAMP + 2),
            max_nonce=100_000,
        )
        assert block is not None and chain.add_block(block, current_time=NOW)
        assert append_ram_tip(reopened, chain, 2) == 3
    finally:
        reopened.close()
    reopened, recovered = open_store(path)
    try:
        assert recovered.blocks[-1].transactions[1].timestamp == 2**80
        assert recovered.blocks[-1].transactions[1].txid() == transaction.txid()
        assert transaction.txid() in recovered.state.seen_txids
        assert len(recovered.mempool) == 0
    finally:
        reopened.close()


@pytest.mark.parametrize("name,limit", [("max_transactions", 7), ("max_bytes", 7000), ("max_transactions", 2**80), ("max_bytes", 2**80)])
def test_config_is_saved_as_exact_decimal_and_inherited_on_reopen(tmp_path, name, limit):
    path = tmp_path / "limits.sqlite"
    store, recovered = open_store(path, **{name: limit})
    assert getattr(recovered.mempool, name) == limit
    store.close()
    assert query(path, f"SELECT mempool_{name}, typeof(mempool_{name}) FROM metadata") == [(str(limit), "text")]
    reopened, recovered = open_store(path)
    assert getattr(recovered.mempool, name) == limit
    reopened.close()
    explicit, recovered = open_store(path, **{name: limit})
    assert getattr(recovered.mempool, name) == limit
    explicit.close()


@pytest.mark.parametrize("name", ["max_transactions", "max_bytes"])
def test_explicit_config_mismatch_fails_without_rewriting_or_dropping_data(funded, name):
    path, store, _, _, _ = make_pending_family(funded)
    store.close()
    before = logical_snapshot(path)
    with pytest.raises(StorageConfigurationError):
        open_store(path, **{name: 1})
    assert logical_snapshot(path) == before
    reopened, recovered = open_store(path)
    assert len(recovered.mempool) == 2
    reopened.close()


@pytest.mark.parametrize("name", ["max_transactions", "max_bytes"])
@pytest.mark.parametrize("value", [True, False, 0, -1, 1.0, "1"])
def test_invalid_limits_fail_before_creating_database(tmp_path, name, value):
    path = tmp_path / "must-not-exist.sqlite"
    store = SQLiteChainStore(path)
    with pytest.raises(ValueError, match=name):
        store.load_or_initialize(**{name: value})
    assert not path.exists()
    store.close()


@pytest.mark.parametrize("value", [True, False, -1, 1.0, "1"])
def test_invalid_current_time_fails_before_creating_database(tmp_path, value):
    path = tmp_path / "must-not-exist.sqlite"
    store = SQLiteChainStore(path)
    with pytest.raises(ValueError, match="current_time"):
        store.load_or_initialize(current_time=value)
    assert not path.exists()
    store.close()


@pytest.mark.parametrize("path", ["", "   ", ":memory:", "file:chain.sqlite?mode=memory", "a\x00b"])
def test_invalid_path_strings_rejected(path):
    with pytest.raises(ValueError):
        SQLiteChainStore(path)


@pytest.mark.parametrize("path", [None, 42, b"chain.sqlite"])
def test_nontext_paths_rejected(path):
    with pytest.raises(TypeError):
        SQLiteChainStore(path)


def test_directory_and_missing_parent_rejected_without_creating_directories(tmp_path):
    with pytest.raises(ValueError):
        SQLiteChainStore(tmp_path)
    with pytest.raises(ValueError):
        SQLiteChainStore(tmp_path / "missing" / "chain.sqlite")
    assert not (tmp_path / "missing").exists()


@pytest.mark.parametrize("contents", [b"", b"not a database", b"SQLite format 3\x00truncated"])
def test_existing_empty_corrupt_or_truncated_file_is_never_initialized(tmp_path, contents):
    path = tmp_path / "foreign.sqlite"
    path.write_bytes(contents)
    with pytest.raises(StorageCorruptionError):
        open_store(path)
    assert path.read_bytes() == contents


def test_existing_foreign_database_is_not_overwritten(tmp_path):
    path = tmp_path / "foreign.sqlite"
    edit(path, "CREATE TABLE unrelated(value TEXT)")
    edit(path, "INSERT INTO unrelated VALUES ('user data')")
    assert_corrupt(path)
    assert query(path, "SELECT * FROM unrelated") == [("user data",)]
    assert query(path, "SELECT name FROM sqlite_schema WHERE type='table'") == [("unrelated",)]


def test_file_created_between_store_constructor_and_load_is_treated_as_existing(tmp_path):
    path = tmp_path / "race.sqlite"
    store = SQLiteChainStore(path)
    edit(path, "CREATE TABLE user_data(value TEXT)")
    with pytest.raises(StorageCorruptionError):
        store.load_or_initialize(current_time=NOW)
    assert query(path, "SELECT name FROM sqlite_schema WHERE type='table'") == [("user_data",)]


@pytest.mark.parametrize("sql", [
    "CREATE TABLE extra(value TEXT)",
    "CREATE VIEW extra AS SELECT * FROM blocks",
    "CREATE TRIGGER extra AFTER INSERT ON blocks BEGIN DELETE FROM mempool; END",
    "CREATE INDEX extra ON blocks(previous_hash)",
    "ALTER TABLE blocks ADD COLUMN extra TEXT",
    "DROP TABLE mempool",
])
def test_unknown_or_changed_schema_rejected(stored, sql):
    path, store, _ = stored
    store.close()
    edit(path, sql)
    assert_corrupt(path, match="schema")


def test_missing_sql_constraint_rejected_even_with_unchanged_columns(stored):
    path, store, _ = stored
    store.close()
    with closing(sqlite3.connect(path)) as connection:
        connection.execute("ALTER TABLE mempool RENAME TO old_mempool")
        connection.execute("CREATE TABLE mempool (position INTEGER PRIMARY KEY, txid TEXT NOT NULL UNIQUE, data BLOB NOT NULL)")
        connection.execute("DROP TABLE old_mempool")
        connection.commit()
    assert_corrupt(path, match="schema")


def test_unsupported_version_is_distinguished_from_corruption(stored):
    path, store, _ = stored
    store.close()
    edit(path, "UPDATE metadata SET schema_version=2")
    with pytest.raises(StorageVersionError):
        open_store(path)


@pytest.mark.parametrize("sql,parameters", [
    ("DELETE FROM metadata", ()),
    ("UPDATE metadata SET genesis_hash=?", ("f" * 64,)),
    ("UPDATE metadata SET tip_hash=?", ("f" * 64,)),
    ("UPDATE metadata SET height=1, revision=1", ()),
    ("UPDATE metadata SET mempool_digest=?", ("f" * 64,)),
])
def test_metadata_corruption_detected(stored, sql, parameters):
    path, store, _ = stored
    store.close()
    edit(path, sql, parameters)
    assert_corrupt(path)


@pytest.mark.parametrize("sql,parameters", [
    ("UPDATE blocks SET hash=? WHERE height=1", ("f" * 64,)),
    ("UPDATE blocks SET previous_hash=? WHERE height=1", ("f" * 64,)),
    ("UPDATE blocks SET data=? WHERE height=1", (b"{}",)),
    ("UPDATE blocks SET height=2 WHERE height=1", ()),
    ("DELETE FROM blocks WHERE height=1", ()),
    ("UPDATE metadata SET revision=0", ()),
])
def test_block_rows_and_committed_prefix_corruption_detected(funded, sql, parameters):
    path, store, _, _ = funded
    store.close()
    edit(path, sql, parameters)
    assert_corrupt(path)


@pytest.mark.parametrize("mutation", ["missing_utxo", "wrong_amount", "wrong_address", "extra_utxo", "missing_seen", "extra_seen"])
def test_confirmed_cache_mismatch_fails_full_replay_comparison(funded, mutation):
    path, store, _, funding = funded
    store.close()
    if mutation == "missing_utxo":
        edit(path, "DELETE FROM utxos")
    elif mutation == "wrong_amount":
        edit(path, "UPDATE utxos SET amount='49'")
    elif mutation == "wrong_address":
        other = public_key_to_address(SigningKey.from_secret_exponent(42, curve=SECP256k1).get_verifying_key())
        edit(path, "UPDATE utxos SET recipient_address=?", (other,))
    elif mutation == "extra_utxo":
        edit(path, "INSERT INTO utxos VALUES (?, 1, '1', ?)", (funding.txid(), ADDRESS))
    elif mutation == "missing_seen":
        edit(path, "DELETE FROM seen_transactions")
    else:
        edit(path, "INSERT INTO seen_transactions VALUES (?)", ("f" * 64,))
    assert_corrupt(path)


def test_persisted_invalid_consensus_block_rejected_even_with_matching_indexes(funded):
    path, store, chain, _ = funded
    store.close()
    block = chain.get_latest_block()
    block.transactions[0].outputs[0].amount = 51
    block.refresh_merkle_root()
    block = mine_block(block, max_nonce=100_000)
    assert block is not None
    edit(path, "UPDATE blocks SET hash=?, data=? WHERE height=1", (block.hash(), encode_block(block)))
    edit(path, "UPDATE metadata SET tip_hash=?", (block.hash(),))
    assert_corrupt(path, match="consensus replay")


def test_clock_rollback_has_context_and_does_not_disable_future_time_validation(funded):
    path, store, _, _ = funded
    store.close()
    with pytest.raises(StorageCorruptionError, match="future timestamp relative to current_time"):
        SQLiteChainStore(path).load_or_initialize(current_time=0)


@pytest.mark.parametrize("mutation", ["tail_deleted", "all_deleted", "gap", "wrong_txid", "malformed", "invalid_signature", "orphan", "coinbase", "over_count", "over_bytes"])
def test_mempool_corruption_is_not_silently_dropped(funded, mutation):
    path, store, chain, parent, child = make_pending_family(funded)
    store.close()
    if mutation == "tail_deleted":
        edit(path, "DELETE FROM mempool WHERE position=1")
    elif mutation == "all_deleted":
        edit(path, "DELETE FROM mempool")
    elif mutation == "gap":
        edit(path, "UPDATE mempool SET position=2 WHERE position=1")
    elif mutation == "wrong_txid":
        edit(path, "UPDATE mempool SET txid=? WHERE position=0", ("f" * 64,))
    elif mutation == "malformed":
        edit(path, "UPDATE mempool SET data=? WHERE position=0", (b"{}",))
    elif mutation == "invalid_signature":
        invalid = deepcopy(child)
        invalid.inputs[0].signature = "aa"
        edit(path, "UPDATE mempool SET txid=?, data=? WHERE position=1", (invalid.txid(), encode_transaction(invalid)))
    elif mutation == "orphan":
        edit(path, "DELETE FROM mempool WHERE position=0")
        edit(path, "UPDATE mempool SET position=0 WHERE position=1")
    elif mutation == "coinbase":
        coinbase = chain.chain[1].transactions[0]
        edit(path, "UPDATE mempool SET txid=?, data=? WHERE position=0", (coinbase.txid(), encode_transaction(coinbase)))
    elif mutation == "over_count":
        edit(path, "UPDATE metadata SET mempool_max_transactions='1'")
    else:
        edit(path, "UPDATE metadata SET mempool_max_bytes='1'")
    before = logical_snapshot(path)
    assert_corrupt(path)
    assert logical_snapshot(path) == before


def test_independent_pending_reorder_breaks_committed_digest(funded):
    path, store, chain, funding = funded
    second_block = mine_block(chain.create_block_template(ADDRESS, timestamp=GENESIS_TIMESTAMP + 2), max_nonce=100_000)
    assert second_block is not None and chain.add_block(second_block, current_time=NOW)
    assert append_ram_tip(store, chain, 1) == 2
    first = transfer(funding)
    second = transfer(second_block.transactions[0])
    assert chain.submit_transaction(first)
    assert chain.submit_transaction(second)
    assert save_pending(store, chain, 2) == 3
    store.close()
    with closing(sqlite3.connect(path)) as connection:
        connection.execute("UPDATE mempool SET position=position+2")
        connection.execute("UPDATE mempool SET position=3-position")
        connection.commit()
    assert_corrupt(path, match="digest")


def test_valid_replacement_pending_payload_breaks_committed_digest(funded):
    path, store, chain, funding = funded
    original = transfer(funding)
    assert chain.submit_transaction(original)
    assert save_pending(store, chain, 1) == 2
    store.close()
    replacement = transfer(funding, amount=44, timestamp=124)
    edit(path, "UPDATE mempool SET txid=?, data=? WHERE position=0", (replacement.txid(), encode_transaction(replacement)))
    assert_corrupt(path, match="digest")


def test_pending_conflict_rejected_even_if_digest_is_recomputed(funded):
    path, store, _, parent, _ = make_pending_family(funded)
    store.close()
    competitor = deepcopy(parent)
    competitor.timestamp += 1
    competitor.sign_input(0, KEY)
    edit(path, "UPDATE mempool SET txid=?, data=? WHERE position=1", (competitor.txid(), encode_transaction(competitor)))
    edit(path, "UPDATE metadata SET mempool_digest=?", (sha256_hex(serialize([parent.txid(), competitor.txid()])),))
    assert_corrupt(path, match="conflicting")


def test_stale_revision_blocks_pool_overwrite_even_at_same_height_and_tip(funded):
    path, store, chain, funding = funded
    stale, loaded = open_store(path)
    try:
        assert chain.submit_transaction(transfer(funding))
        assert save_pending(store, chain, 1) == 2
        before = logical_snapshot(path)
        with pytest.raises(StorageConflictError):
            stale.replace_mempool(loaded.mempool, expected_height=1, expected_tip_hash=loaded.blocks[-1].hash(), expected_revision=1)
        assert logical_snapshot(path) == before
    finally:
        stale.close()


def test_stale_revision_blocks_append_after_another_writer_only_changes_pool(funded):
    path, store, chain, funding = funded
    stale, loaded = open_store(path)
    try:
        assert chain.submit_transaction(transfer(funding))
        assert save_pending(store, chain, 1) == 2
        candidate = mine_block(chain.create_block_template(ADDRESS, timestamp=GENESIS_TIMESTAMP + 2), max_nonce=100_000)
        assert candidate is not None and chain.add_block(candidate, current_time=NOW)
        before = logical_snapshot(path)
        with pytest.raises(StorageConflictError):
            append_ram_tip(stale, chain, loaded.revision)
        assert logical_snapshot(path) == before
    finally:
        stale.close()


def test_stale_tip_and_height_block_mempool_replacement(funded):
    path, store, chain, _ = funded
    stale, loaded = open_store(path)
    try:
        candidate = mine_block(chain.create_block_template(ADDRESS, timestamp=GENESIS_TIMESTAMP + 2), max_nonce=100_000)
        assert candidate is not None and chain.add_block(candidate, current_time=NOW)
        assert append_ram_tip(store, chain, 1) == 2
        before = logical_snapshot(path)
        with pytest.raises(StorageConflictError):
            stale.replace_mempool(loaded.mempool, expected_height=1, expected_tip_hash=loaded.blocks[-1].hash(), expected_revision=1)
        assert logical_snapshot(path) == before
    finally:
        stale.close()


@pytest.mark.parametrize("helper", ["insert_block_row", "replace_chainstate_rows", "replace_mempool_rows", "update_metadata"])
def test_append_write_failure_rolls_back_all_five_tables(funded, monkeypatch, helper):
    path, store, chain, _ = funded
    candidate = mine_block(chain.create_block_template(ADDRESS, timestamp=GENESIS_TIMESTAMP + 2), max_nonce=100_000)
    assert candidate is not None and chain.add_block(candidate, current_time=NOW)
    before = logical_snapshot(path)
    module = block_store if helper == "insert_block_row" else chainstate_store
    original = getattr(module, helper)
    def fail_after_write(*args, **kwargs):
        original(*args, **kwargs)
        raise sqlite3.OperationalError("injected SQL failure")
    monkeypatch.setattr(module, helper, fail_after_write)
    with pytest.raises(StorageError) as failure:
        append_ram_tip(store, chain, 1)
    assert not isinstance(failure.value, StorageCommitUncertainError)
    assert not store._connection.in_transaction
    assert logical_snapshot(path) == before
    store.close()
    reopened, recovered = open_store(path)
    assert len(recovered.blocks) == 2 and recovered.revision == 1
    reopened.close()


@pytest.mark.parametrize("exception_type", [RuntimeError, KeyboardInterrupt, SystemExit])
def test_pool_replacement_rolls_back_on_baseexception(funded, monkeypatch, exception_type):
    path, store, chain, parent, _ = make_pending_family(funded)
    assert chain.remove_pending_transaction(parent.txid())
    before = logical_snapshot(path)
    original = chainstate_store.replace_mempool_rows
    def fail_after_write(*args):
        original(*args)
        raise exception_type("interrupted replacement")
    monkeypatch.setattr(chainstate_store, "replace_mempool_rows", fail_after_write)
    with pytest.raises(exception_type):
        save_pending(store, chain, 2)
    assert not store._connection.in_transaction
    assert logical_snapshot(path) == before


@pytest.mark.parametrize("after_commit", [False, True])
def test_commit_failure_reports_uncertain_and_reopen_determines_result(funded, monkeypatch, after_commit):
    path, store, chain, funding = funded
    pending = transfer(funding)
    assert chain.submit_transaction(pending)
    original = database.commit_transaction
    def fail_commit(connection):
        if after_commit:
            original(connection)
        raise sqlite3.OperationalError("commit boundary failure")
    monkeypatch.setattr(database, "commit_transaction", fail_commit)
    with pytest.raises(StorageCommitUncertainError):
        save_pending(store, chain, 1)
    store.close()
    monkeypatch.setattr(database, "commit_transaction", original)
    reopened, recovered = open_store(path)
    assert recovered.revision == (2 if after_commit else 1)
    assert recovered.mempool.get_transactions() == ([pending] if after_commit else [])
    reopened.close()


def test_initialization_failure_rolls_back_schema_and_never_reinitializes_empty_file(tmp_path, monkeypatch):
    path = tmp_path / "failed.sqlite"
    original = chainstate_store.insert_metadata
    def fail(*args):
        original(*args)
        raise sqlite3.OperationalError("init failure")
    monkeypatch.setattr(chainstate_store, "insert_metadata", fail)
    with pytest.raises(StorageError):
        open_store(path)
    assert query(path, "SELECT name FROM sqlite_schema") == []
    monkeypatch.setattr(chainstate_store, "insert_metadata", original)
    assert_corrupt(path)


def test_preencoding_failure_happens_before_any_sql_write(funded, monkeypatch):
    path, store, chain, _ = funded
    candidate = mine_block(chain.create_block_template(ADDRESS, timestamp=GENESIS_TIMESTAMP + 2), max_nonce=100_000)
    assert candidate is not None and chain.add_block(candidate, current_time=NOW)
    before = logical_snapshot(path)
    statements = []
    store._connection.set_trace_callback(statements.append)
    def fail(_):
        raise StorageError("encoding failed")
    monkeypatch.setattr(chainstate_store, "encode_chainstate_rows", fail)
    with pytest.raises(StorageError, match="encoding"):
        append_ram_tip(store, chain, 1)
    assert statements == []
    assert logical_snapshot(path) == before


def test_lock_timeout_is_storage_error_and_preserves_database(funded):
    path, store, chain, funding = funded
    assert chain.submit_transaction(transfer(funding))
    before = logical_snapshot(path)
    # Shorten only this test connection's wait to avoid a five-second test.
    store._connection.execute("PRAGMA busy_timeout=1")
    with closing(sqlite3.connect(path, isolation_level=None)) as blocker:
        blocker.execute("BEGIN IMMEDIATE")
        try:
            with pytest.raises(StorageError) as failure:
                save_pending(store, chain, 1)
            assert isinstance(failure.value.__cause__, sqlite3.OperationalError)
            assert not isinstance(failure.value, StorageCommitUncertainError)
        finally:
            blocker.execute("ROLLBACK")
    assert logical_snapshot(path) == before


def test_existing_wal_database_is_rejected_without_changing_mode(stored):
    path, store, _ = stored
    store.close()
    with closing(sqlite3.connect(path)) as connection:
        assert connection.execute("PRAGMA journal_mode=WAL").fetchone()[0] == "wal"
    with pytest.raises(StorageError, match="journal_mode"):
        open_store(path)
    assert query(path, "PRAGMA journal_mode") == [("wal",)]


def test_decimal_amount_helper_keeps_large_python_integer(stored):
    _, store, _ = stored
    state = ChainState()
    state.seen_txids.add("a" * 64)
    state.utxo_set.add("a" * 64, 0, TxOutput(2**80, ADDRESS))
    connection = store._connection
    connection.execute("BEGIN")
    try:
        chainstate_store.replace_chainstate_rows(connection, chainstate_store.encode_chainstate_rows(state))
        assert connection.execute("SELECT amount, typeof(amount) FROM utxos").fetchall() == [(str(2**80), "text")]
        assert chainstate_store.read_chainstate_rows(connection).utxo_set.get_balance(ADDRESS) == 2**80
    finally:
        connection.execute("ROLLBACK")


def test_closed_store_rejects_operations_and_close_is_idempotent(stored):
    _, store, recovered = stored
    store.close()
    store.close()
    with pytest.raises(StorageClosedError):
        store.load_or_initialize()
    with pytest.raises(StorageClosedError):
        store.replace_mempool(recovered.mempool, expected_height=0, expected_tip_hash=GENESIS_HASH, expected_revision=0)
    with pytest.raises(StorageClosedError):
        store.append_block(recovered.blocks[0], recovered.state, recovered.mempool, expected_height=0, expected_tip_hash=GENESIS_HASH, expected_revision=0)


def test_startup_snapshot_uses_one_read_transaction(stored, monkeypatch):
    path, store, _ = stored
    store.close()
    observed = []
    original = database.validate_schema
    def validate(connection):
        assert connection.in_transaction
        connection.set_trace_callback(observed.append)
        original(connection)
    monkeypatch.setattr(database, "validate_schema", validate)
    reopened, _ = open_store(path)
    assert observed[-1] == "COMMIT"
    assert not any(statement in ("BEGIN", "BEGIN IMMEDIATE", "ROLLBACK") for statement in observed)
    assert any("integrity_check" in statement for statement in observed)
    assert any("FROM mempool" in statement for statement in observed)
    reopened.close()


def test_cleanup_failure_does_not_mask_original_startup_error(stored, monkeypatch):
    path, store, _ = stored
    store.close()
    failing = SQLiteChainStore(path)
    original_close = failing.close
    def corrupt(_):
        raise StorageCorruptionError("original corruption")
    def close_then_fail():
        original_close()
        raise StorageError("cleanup failure")
    monkeypatch.setattr(database, "validate_schema", corrupt)
    monkeypatch.setattr(failing, "close", close_then_fail)
    with pytest.raises(StorageCorruptionError, match="original corruption"):
        failing.load_or_initialize(current_time=NOW)
    assert failing._closed and failing._connection is None
