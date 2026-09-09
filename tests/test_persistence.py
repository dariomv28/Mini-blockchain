from copy import deepcopy
from fractions import Fraction
from pathlib import Path
import subprocess
import sys

import pytest
from ecdsa import SECP256k1, SigningKey

from blockchain.block import Block
from blockchain.blockchain import Blockchain
from blockchain.genesis import GENESIS_TIMESTAMP
from consensus.difficulty import MINING_DIFFICULTY
from consensus.pow import validate_proof_of_work
from crypto.address import public_key_to_address
from crypto.hash import serialize
from mining.coinbase import create_coinbase_transaction
from mining.miner import mine_block
from storage.errors import (
    StorageClosedError,
    StorageCommitUncertainError,
    StorageConfigurationError,
    StorageConflictError,
    StorageCorruptionError,
    StorageError,
)
from transaction.transaction import Transaction
from transaction.tx_input import TxInput
from transaction.tx_output import TxOutput


NOW = GENESIS_TIMESTAMP + 100
ALICE_KEY = SigningKey.from_secret_exponent(31, curve=SECP256k1)
BOB_KEY = SigningKey.from_secret_exponent(32, curve=SECP256k1)
CAROL_KEY = SigningKey.from_secret_exponent(33, curve=SECP256k1)
MINER_KEY = SigningKey.from_secret_exponent(34, curve=SECP256k1)
ALICE = public_key_to_address(ALICE_KEY.get_verifying_key())
BOB = public_key_to_address(BOB_KEY.get_verifying_key())
CAROL = public_key_to_address(CAROL_KEY.get_verifying_key())
MINER = public_key_to_address(MINER_KEY.get_verifying_key())
ADDRESSES = (ALICE, BOB, CAROL, MINER)


def mine(template: Block) -> Block:
    mined = mine_block(template, max_nonce=100_000)
    assert mined is not None
    return mined


def funded_chain(db_path, **configuration) -> tuple[Blockchain, Transaction]:
    chain = Blockchain(db_path=db_path, current_time=NOW, **configuration)
    block = mine(chain.create_block_template(ALICE, timestamp=GENESIS_TIMESTAMP + 1))
    assert chain.add_block(block, current_time=NOW)
    return chain, block.transactions[0]


def transfer(source, private_key, outputs, *, output_index=0) -> Transaction:
    transaction = Transaction(
        inputs=[TxInput(source.txid(), output_index)],
        outputs=[TxOutput(amount, address) for amount, address in outputs],
        timestamp=GENESIS_TIMESTAMP + 10,
    )
    transaction.sign_input(0, private_key)
    return transaction


def pending_branch(chain, funding) -> tuple[Transaction, Transaction]:
    parent = transfer(funding, ALICE_KEY, [(45, BOB)])
    child = transfer(parent, BOB_KEY, [(40, CAROL)])
    assert chain.submit_transaction(parent)
    assert chain.submit_transaction(child)
    return parent, child


def candidate_from_pool(chain, **limits) -> Block:
    return mine(
        chain.create_mempool_block_template(
            MINER, timestamp=chain.get_latest_block().timestamp + 1, **limits
        )
    )


def raw_candidate(chain, transactions, *, reward=50) -> Block:
    parent = chain.get_latest_block()
    timestamp = parent.timestamp + 1
    coinbase = create_coinbase_transaction(MINER, timestamp=timestamp)
    coinbase.outputs[0].amount = reward
    return mine(
        Block(
            transactions=deepcopy([coinbase, *transactions]),
            previous_block_hash=parent.hash(),
            timestamp=timestamp,
            difficulty=MINING_DIFFICULTY,
        )
    )


def snapshot(chain, *tracked_txids):
    blocks = chain.chain
    pool = chain.mempool
    entries = []
    tracked = set(tracked_txids)
    for block in blocks:
        tracked.update(transaction.txid() for transaction in block.transactions)
    for transaction in pool.get_transactions():
        txid = transaction.txid()
        tracked.add(txid)
        entry = pool.get_entry(txid)
        entries.append((transaction.to_dict(), entry.fee, entry.size_bytes, entry.fee_rate))
    return (
        [block.to_dict() for block in blocks],
        chain.utxo_set.to_dict(),
        {address: chain.get_balance(address) for address in ADDRESSES},
        {txid: chain.has_transaction(txid) for txid in tracked},
        entries,
        pool.total_bytes,
        pool.max_transactions,
        pool.max_bytes,
        chain._revision,
    )


def private_snapshot(chain):
    """Inspect publication after public access is correctly blocked by failure."""
    return deepcopy(
        (
            [block.to_dict() for block in chain._blocks],
            chain._state.utxo_set.to_dict(),
            chain._state.seen_txids,
            [transaction.to_dict() for transaction in chain._mempool.get_transactions()],
            chain._mempool.total_bytes,
            chain._revision,
        )
    )


def read_disk(db_path, *tracked_txids):
    with Blockchain(db_path=db_path, current_time=NOW) as reopened:
        return snapshot(reopened, *tracked_txids)


def public_operations(chain):
    return (
        lambda: len(chain),
        lambda: chain.height,
        lambda: chain.chain,
        lambda: chain.utxo_set,
        lambda: chain.mempool,
        lambda: chain.get_balance(ALICE),
        lambda: chain.get_utxos_for_address(ALICE),
        lambda: chain.has_transaction("f" * 64),
        lambda: chain.get_latest_block(),
        lambda: chain.get_block_by_height(0),
        lambda: chain.get_block_by_hash("f" * 64),
        lambda: chain.create_block_template(MINER, timestamp=GENESIS_TIMESTAMP + 2),
        lambda: chain.create_mempool_block_template(MINER, timestamp=GENESIS_TIMESTAMP + 2),
        lambda: chain.submit_transaction(None),
        lambda: chain.remove_pending_transaction("f" * 64),
        lambda: chain.add_block(None, current_time=NOW),
        lambda: chain.validate_chain(current_time=NOW),
        lambda: chain.__enter__(),
    )


def test_restart_restores_confirmed_state_and_pending_order_fees_and_dependencies(tmp_path):
    db_path = tmp_path / "chain.sqlite3"
    chain, funding = funded_chain(db_path)
    parent, child = pending_branch(chain, funding)
    expected = snapshot(chain)
    chain.close()

    with Blockchain(db_path=str(db_path), current_time=NOW) as reopened:
        assert snapshot(reopened) == expected
        assert reopened.height == 1
        assert reopened.get_balance(ALICE) == 50
        assert reopened.get_balance(BOB) == 0
        assert reopened.has_transaction(funding.txid())
        assert not reopened.has_transaction(parent.txid())
        pool = reopened.mempool
        assert [tx.txid() for tx in pool.get_transactions()] == [parent.txid(), child.txid()]
        for transaction in (parent, child):
            entry = pool.get_entry(transaction.txid())
            size = len(serialize(transaction.to_dict()))
            assert entry.fee == 5
            assert entry.size_bytes == size
            assert entry.fee_rate == Fraction(5, size)
        candidate = candidate_from_pool(reopened)
        assert candidate.transactions[0].outputs[0].amount == 60
        assert reopened.add_block(candidate, current_time=NOW)
        assert reopened.get_balance(CAROL) == 40
        assert reopened.validate_chain(current_time=NOW)


def test_confirmed_parent_and_surviving_child_are_durable_across_restart(tmp_path):
    db_path = tmp_path / "partial.sqlite3"
    chain, funding = funded_chain(db_path)
    parent, child = pending_branch(chain, funding)
    assert chain.add_block(candidate_from_pool(chain, max_transactions=1), current_time=NOW)
    expected = snapshot(chain)
    chain.close()

    with Blockchain(db_path=db_path, current_time=NOW) as reopened:
        assert snapshot(reopened) == expected
        assert reopened.has_transaction(parent.txid())
        assert not reopened.has_transaction(child.txid())
        assert reopened.get_balance(BOB) == 45
        assert [tx.txid() for tx in reopened.mempool.get_transactions()] == [child.txid()]
        assert reopened.add_block(candidate_from_pool(reopened), current_time=NOW)
        assert reopened.get_balance(CAROL) == 40
        assert len(reopened.mempool) == 0
        confirmed = snapshot(reopened)
    assert read_disk(db_path) == confirmed


def test_competing_external_block_persists_eviction_and_retains_unrelated_pool_entry(tmp_path):
    db_path = tmp_path / "external.sqlite3"
    chain, funding = funded_chain(db_path)
    split = transfer(funding, ALICE_KEY, [(25, ALICE), (24, BOB)])
    assert chain.add_block(raw_candidate(chain, [split], reward=51), current_time=NOW)
    parent = transfer(split, ALICE_KEY, [(23, ALICE)])
    child = transfer(parent, ALICE_KEY, [(22, CAROL)])
    unrelated = transfer(split, BOB_KEY, [(20, CAROL)], output_index=1)
    for transaction in (parent, child, unrelated):
        assert chain.submit_transaction(transaction)
    external = transfer(split, ALICE_KEY, [(21, CAROL)])

    assert chain.add_block(raw_candidate(chain, [external], reward=54), current_time=NOW)
    expected = snapshot(chain, parent.txid(), child.txid())
    chain.close()
    with Blockchain(db_path=db_path, current_time=NOW) as reopened:
        assert snapshot(reopened, parent.txid(), child.txid()) == expected
        assert reopened.has_transaction(external.txid())
        assert [tx.txid() for tx in reopened.mempool.get_transactions()] == [unrelated.txid()]
        assert reopened.get_balance(CAROL) == 21
        assert reopened.add_block(candidate_from_pool(reopened), current_time=NOW)
        assert reopened.get_balance(CAROL) == 41


def test_submit_and_cascading_remove_are_durable_but_noops_never_advance_revision(tmp_path):
    db_path = tmp_path / "pool.sqlite3"
    chain, funding = funded_chain(db_path)
    parent, child = pending_branch(chain, funding)
    expected = snapshot(chain)
    assert read_disk(db_path) == expected

    assert not chain.submit_transaction(parent)
    assert not chain.remove_pending_transaction("f" * 64)
    assert snapshot(chain) == expected
    assert read_disk(db_path) == expected
    assert chain.remove_pending_transaction(parent.txid())
    removed = snapshot(chain, parent.txid(), child.txid())
    assert removed[-1] == expected[-1] + 1
    assert len(chain.mempool) == 0
    assert chain.get_balance(ALICE) == 50
    assert read_disk(db_path, parent.txid(), child.txid()) == removed
    chain.close()


@pytest.mark.parametrize("defect", ["bad_signature", "invalid_suffix", "overclaim", "invalid_pow"])
def test_rejected_transaction_or_block_changes_neither_disk_nor_ram(tmp_path, defect):
    db_path = tmp_path / f"rejected_{defect}.sqlite3"
    chain, funding = funded_chain(db_path)
    parent, child = pending_branch(chain, funding)
    if defect == "bad_signature":
        invalid = transfer(child, CAROL_KEY, [(39, ALICE)])
        invalid.inputs[0].signature = "00" * 64
        tracked = (invalid.txid(),)
        reject = lambda: chain.submit_transaction(invalid)
    else:
        transactions = [parent, child]
        if defect == "invalid_suffix":
            transactions.append(transfer(child, CAROL_KEY, [(41, ALICE)]))
        candidate = raw_candidate(chain, transactions, reward=61 if defect == "overclaim" else 60)
        if defect == "invalid_pow":
            while validate_proof_of_work(candidate):
                candidate.nonce += 1
        tracked = tuple(transaction.txid() for transaction in candidate.transactions)
        reject = lambda: chain.add_block(candidate, current_time=NOW)
    expected = snapshot(chain, *tracked)

    assert not reject()
    assert snapshot(chain, *tracked) == expected
    assert read_disk(db_path, *tracked) == expected
    assert chain.add_block(candidate_from_pool(chain), current_time=NOW)
    assert chain.get_balance(CAROL) == 40
    chain.close()


def test_templates_mining_and_exported_snapshots_never_persist_mutations(tmp_path):
    db_path = tmp_path / "snapshots.sqlite3"
    chain, funding = funded_chain(db_path)
    parent, child = pending_branch(chain, funding)
    expected = snapshot(chain)

    chain.chain[-1].transactions[0].outputs[0].amount = 999
    chain.get_latest_block().transactions[0].outputs[0].amount = 998
    chain.utxo_set.spend(funding.txid(), 0)
    chain.get_utxos_for_address(ALICE)[(funding.txid(), 0)].amount = 997
    detached = chain.mempool
    assert detached.remove_transaction(parent.txid())
    chain.mempool.get_entry(child.txid()).transaction.outputs[0].amount = 996
    candidate_from_pool(chain).transactions[0].outputs[0].amount = 995
    parent.outputs[0].amount = 994

    assert snapshot(chain) == expected
    assert read_disk(db_path) == expected
    chain.close()


def test_restart_restores_pool_limits_and_accepts_explicit_matching_limits(tmp_path):
    db_path = tmp_path / "configuration.sqlite3"
    chain, funding = funded_chain(
        db_path, mempool_max_transactions=7, mempool_max_bytes=12_345
    )
    pending_branch(chain, funding)
    expected = snapshot(chain)
    chain.close()

    assert read_disk(db_path) == expected
    with Blockchain(
        db_path=db_path,
        current_time=NOW,
        mempool_max_transactions=7,
        mempool_max_bytes=12_345,
    ) as reopened:
        assert snapshot(reopened) == expected


@pytest.mark.parametrize(
    "configuration",
    [{"mempool_max_transactions": 8}, {"mempool_max_bytes": 12_346}],
)
def test_existing_database_rejects_different_explicit_limits_without_overwriting(tmp_path, configuration):
    db_path = tmp_path / "mismatch.sqlite3"
    chain, funding = funded_chain(
        db_path, mempool_max_transactions=7, mempool_max_bytes=12_345
    )
    pending_branch(chain, funding)
    expected = snapshot(chain)
    chain.close()

    with pytest.raises(StorageConfigurationError):
        Blockchain(db_path=db_path, current_time=NOW, **configuration)
    assert read_disk(db_path) == expected


@pytest.mark.parametrize("operation", ["submit", "remove", "append"])
def test_stale_writer_cannot_overwrite_a_newer_pool_revision_at_the_same_tip(tmp_path, operation):
    db_path = tmp_path / f"stale_{operation}.sqlite3"
    first, funding = funded_chain(db_path)
    parent = transfer(funding, ALICE_KEY, [(45, BOB)])
    child = transfer(parent, BOB_KEY, [(40, CAROL)])
    assert first.submit_transaction(parent)
    stale = Blockchain(db_path=db_path, current_time=NOW)
    assert first.submit_transaction(child)
    assert first.height == stale.height
    assert first.get_latest_block().hash() == stale.get_latest_block().hash()
    assert first._revision > stale._revision
    expected = snapshot(first)
    stale_before = private_snapshot(stale)
    if operation == "submit":
        competitor = transfer(parent, BOB_KEY, [(39, ALICE)])
        mutate = lambda: stale.submit_transaction(competitor)
    elif operation == "remove":
        mutate = lambda: stale.remove_pending_transaction(parent.txid())
    else:
        candidate = candidate_from_pool(stale)
        mutate = lambda: stale.add_block(candidate, current_time=NOW)

    with pytest.raises(StorageConflictError):
        mutate()
    assert private_snapshot(stale) == stale_before
    for access in public_operations(stale):
        with pytest.raises(StorageError):
            access()
    assert read_disk(db_path) == expected
    assert snapshot(first) == expected
    stale.close()
    first.close()


def test_persistent_context_exit_closes_every_public_operation_and_close_is_idempotent(tmp_path):
    db_path = tmp_path / "closed.sqlite3"
    with Blockchain(db_path=db_path, current_time=NOW) as chain:
        assert chain.height == 0
        expected = snapshot(chain)
    chain.close()
    for operation in public_operations(chain):
        with pytest.raises(StorageClosedError):
            operation()
    assert read_disk(db_path) == expected


def test_context_closes_database_even_when_body_raises(tmp_path):
    db_path = tmp_path / "context_failure.sqlite3"
    with pytest.raises(RuntimeError, match="body failed"):
        with Blockchain(db_path=db_path, current_time=NOW) as chain:
            raise RuntimeError("body failed")
    with pytest.raises(StorageClosedError):
        chain.get_latest_block()
    with Blockchain(db_path=db_path, current_time=NOW) as reopened:
        assert reopened.height == 0


def test_constructor_preserves_load_error_when_store_cleanup_also_fails(tmp_path, monkeypatch):
    original_error = StorageCorruptionError("original load failure")
    cleanup_calls = []

    class BrokenStore:
        def load_or_initialize(self, **configuration):
            raise original_error

        def close(self):
            cleanup_calls.append("close")
            raise StorageError("secondary cleanup failure")

    with monkeypatch.context() as patch:
        patch.setattr("blockchain.blockchain.SQLiteChainStore", lambda path: BrokenStore())
        with pytest.raises(StorageCorruptionError, match="original load failure") as raised:
            Blockchain(db_path=tmp_path / "unopened.sqlite3", current_time=NOW)

    assert raised.value is original_error
    assert cleanup_calls == ["close"]
    if hasattr(original_error, "add_note"):
        assert any("secondary cleanup failure" in note for note in original_error.__notes__)
    assert list(tmp_path.iterdir()) == []


def test_context_preserves_body_error_when_real_store_close_also_raises(tmp_path, monkeypatch):
    db_path = tmp_path / "cleanup_failure.sqlite3"
    chain = Blockchain(db_path=db_path, current_time=NOW)
    expected = snapshot(chain)
    original_close = chain._store.close
    body_error = ValueError("original body failure")

    def close_then_fail():
        original_close()
        raise StorageError("secondary close failure")

    with monkeypatch.context() as patch:
        patch.setattr(chain._store, "close", close_then_fail)
        with pytest.raises(ValueError, match="original body failure") as raised:
            with chain:
                raise body_error

    assert raised.value is body_error
    if hasattr(body_error, "add_note"):
        assert any("secondary close failure" in note for note in body_error.__notes__)
    with pytest.raises(StorageClosedError):
        chain.get_latest_block()
    assert read_disk(db_path) == expected


def test_default_memory_mode_creates_no_files_and_close_is_a_noop(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    chain, funding = funded_chain(None)
    parent, child = pending_branch(chain, funding)
    chain.close()
    chain.close()
    assert chain.get_balance(ALICE) == 50
    assert chain.mempool.has_transaction(parent.txid())
    assert chain.mempool.has_transaction(child.txid())
    assert chain.add_block(candidate_from_pool(chain), current_time=NOW)
    assert chain.get_balance(CAROL) == 40
    assert list(tmp_path.iterdir()) == []


@pytest.mark.parametrize("path", ["", "   ", ":memory:", "file:chain.sqlite3", 42, b"chain.sqlite3"])
def test_invalid_database_path_is_rejected_without_creating_files(tmp_path, monkeypatch, path):
    monkeypatch.chdir(tmp_path)
    with pytest.raises((StorageConfigurationError, TypeError, ValueError)):
        Blockchain(db_path=path, current_time=NOW)
    assert list(tmp_path.iterdir()) == []


@pytest.mark.parametrize(
    "configuration",
    [
        {"current_time": -1},
        {"current_time": False},
        {"current_time": 0.0},
        {"mempool_max_transactions": 0},
        {"mempool_max_transactions": True},
        {"mempool_max_bytes": -1},
    ],
)
def test_invalid_runtime_configuration_is_rejected_before_creating_database(tmp_path, configuration):
    db_path = tmp_path / "invalid_configuration.sqlite3"
    with pytest.raises(ValueError):
        Blockchain(db_path=db_path, **configuration)
    assert list(tmp_path.iterdir()) == []


@pytest.mark.parametrize("operation", ["append", "submit", "remove"])
@pytest.mark.parametrize("committed", [False, True], ids=["before_commit", "after_commit"])
def test_storage_failure_blocks_instance_without_publishing_ram_and_reopen_recovers(
    tmp_path, monkeypatch, operation, committed
):
    db_path = tmp_path / f"failure_{operation}_{committed}.sqlite3"
    chain, funding = funded_chain(db_path)
    parent, child = pending_branch(chain, funding)
    tracked = [parent.txid(), child.txid()]
    if operation == "append":
        candidate = candidate_from_pool(chain)
        tracked.extend(transaction.txid() for transaction in candidate.transactions)
        method = "append_block"
        mutate = lambda: chain.add_block(candidate, current_time=NOW)
    elif operation == "submit":
        grandchild = transfer(child, CAROL_KEY, [(39, ALICE)])
        tracked.append(grandchild.txid())
        method = "replace_mempool"
        mutate = lambda: chain.submit_transaction(grandchild)
    else:
        method = "replace_mempool"
        mutate = lambda: chain.remove_pending_transaction(parent.txid())
    expected_before = snapshot(chain, *tracked)
    ram_before = private_snapshot(chain)
    original = getattr(chain._store, method)

    def storage_failure(*args, **kwargs):
        if committed:
            original(*args, **kwargs)
            raise StorageCommitUncertainError("injected failure after durable commit")
        raise StorageError("injected failure before durable commit")

    with monkeypatch.context() as patch:
        patch.setattr(chain._store, method, storage_failure)
        with pytest.raises(StorageError):
            mutate()
    assert private_snapshot(chain) == ram_before
    for access in public_operations(chain):
        with pytest.raises(StorageError):
            access()
    chain.close()

    with Blockchain(db_path=db_path, current_time=NOW) as reopened:
        if not committed:
            assert snapshot(reopened, *tracked) == expected_before
            assert reopened.add_block(candidate_from_pool(reopened), current_time=NOW)
        else:
            assert reopened._revision == expected_before[-1] + 1
            if operation == "append":
                assert reopened.height == 2
                assert reopened.get_balance(CAROL) == 40
                assert len(reopened.mempool) == 0
            elif operation == "submit":
                assert reopened.height == 1
                assert reopened.get_balance(ALICE) == 50
                assert [tx.txid() for tx in reopened.mempool.get_transactions()] == [
                    parent.txid(), child.txid(), grandchild.txid()
                ]
            else:
                assert reopened.height == 1
                assert reopened.get_balance(ALICE) == 50
                assert len(reopened.mempool) == 0
        assert reopened.validate_chain(current_time=NOW)


@pytest.mark.parametrize("operation", ["append", "remove"])
@pytest.mark.parametrize("crash_point", ["before_commit", "after_commit"])
def test_subprocess_crash_recovers_a_complete_pre_or_post_commit_snapshot(
    tmp_path, operation, crash_point
):
    db_path = tmp_path / f"crash_{operation}_{crash_point}.sqlite3"
    chain, funding = funded_chain(db_path)
    parent, child = pending_branch(chain, funding)
    tracked = (parent.txid(), child.txid())
    expected_before = snapshot(chain, *tracked)
    chain.close()

    worker = Path(__file__).with_name("persistence_worker.py")
    completed = subprocess.run(
        [sys.executable, "-B", str(worker), str(db_path), operation, crash_point],
        cwd=Path(__file__).resolve().parents[1],
        stdin=subprocess.DEVNULL,
        capture_output=True,
        text=True,
        timeout=30,
        creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        check=False,
    )
    assert completed.returncode == (71 if crash_point == "before_commit" else 72), (
        completed.stdout + completed.stderr
    )
    with Blockchain(db_path=db_path, current_time=NOW) as reopened:
        if crash_point == "before_commit":
            assert snapshot(reopened, *tracked) == expected_before
            assert reopened.add_block(candidate_from_pool(reopened), current_time=NOW)
        else:
            assert reopened._revision == expected_before[-1] + 1
            assert len(reopened.mempool) == 0
            if operation == "append":
                assert reopened.height == 2
                assert reopened.has_transaction(parent.txid())
                assert reopened.has_transaction(child.txid())
                assert reopened.get_balance(ALICE) == 0
                assert reopened.get_balance(CAROL) == 40
                assert reopened.get_balance(MINER) == 60
            else:
                assert reopened.height == 1
                assert not reopened.has_transaction(parent.txid())
                assert not reopened.has_transaction(child.txid())
                assert reopened.get_balance(ALICE) == 50
                assert reopened.get_balance(CAROL) == 0
        assert reopened.validate_chain(current_time=NOW)
