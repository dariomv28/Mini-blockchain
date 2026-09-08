from copy import deepcopy
from dataclasses import FrozenInstanceError
from fractions import Fraction

import pytest
from ecdsa import SECP256k1, SigningKey

from crypto.address import public_key_to_address
from crypto.hash import serialize
from mining.coinbase import create_coinbase_transaction
from transaction.mempool import (
    DEFAULT_BLOCK_MAX_BYTES,
    DEFAULT_BLOCK_MAX_TRANSACTIONS,
    DEFAULT_MEMPOOL_MAX_BYTES,
    DEFAULT_MEMPOOL_MAX_TRANSACTIONS,
    Mempool,
)
from transaction.transaction import Transaction
from transaction.tx_input import TxInput
from transaction.tx_output import TxOutput
from transaction.utxo import UTXOSet


@pytest.fixture
def funding():
    owner = SigningKey.from_secret_exponent(1, curve=SECP256k1)
    address = public_key_to_address(owner.get_verifying_key())
    utxos = UTXOSet()
    for name in ("funding-a", "funding-b", "funding-c"):
        utxos.add(name, 0, TxOutput(100, address))
    return owner, address, utxos


def spend(funding, source="funding-a", amount=99, *, timestamp=123):
    owner, address, _ = funding
    transaction = Transaction(
        [TxInput(source, 0)], [TxOutput(amount, address)], timestamp=timestamp
    )
    transaction.sign_input(0, owner)
    return transaction


def ids(transactions):
    return [transaction.txid() for transaction in transactions]


def state(pool):
    return pool.get_transactions(), pool.total_bytes


def family(funding):
    parent = spend(funding)
    child = spend(funding, parent.txid(), 89)
    grandchild = spend(funding, child.txid(), 79)
    unrelated = spend(funding, "funding-b", 95)
    return parent, child, grandchild, unrelated


def test_defaults_and_empty_pool(funding):
    pool = Mempool()
    assert DEFAULT_MEMPOOL_MAX_TRANSACTIONS == pool.max_transactions == 1000
    assert DEFAULT_MEMPOOL_MAX_BYTES == pool.max_bytes == 1_000_000
    assert DEFAULT_BLOCK_MAX_TRANSACTIONS == 100
    assert DEFAULT_BLOCK_MAX_BYTES == 100_000
    assert len(pool) == pool.total_bytes == 0
    assert pool.get_transactions() == pool.select_transactions() == []
    assert not pool.add_transaction(spend(funding))


@pytest.mark.parametrize("limit", [0, -1, True, False, 1.0, "1", None])
@pytest.mark.parametrize("name", ["max_transactions", "max_bytes"])
def test_constructor_rejects_invalid_limits(name, limit):
    with pytest.raises(ValueError, match=name):
        Mempool(**{name: limit})


@pytest.mark.parametrize(
    "utxos,seen", [(UTXOSet(), None), (None, set()), ({}, set()), (UTXOSet(), []), (UTXOSet(), {1})]
)
def test_constructor_requires_both_valid_state_arguments(utxos, seen):
    with pytest.raises(ValueError):
        Mempool(utxos, seen)


def test_admission_records_verified_fee_and_signed_canonical_size(funding):
    pool = Mempool(funding[2], set())
    transaction = spend(funding)
    assert pool.add_transaction(transaction)
    entry = pool.get_entry(transaction.txid())
    assert entry.transaction == transaction
    assert entry.fee == 1
    assert entry.size_bytes == len(serialize(transaction.to_dict()))
    assert entry.size_bytes > len(serialize(transaction.to_dict(include_signatures=False)))
    assert entry.fee_rate == Fraction(1, entry.size_bytes)
    assert isinstance(entry.fee_rate, Fraction)
    assert len(pool) == 1
    assert pool.total_bytes == entry.size_bytes
    with pytest.raises(FrozenInstanceError):
        entry.fee = 2


def test_zero_fee_is_allowed(funding):
    transaction = spend(funding, amount=100)
    pool = Mempool(funding[2], set())
    assert pool.add_transaction(transaction)
    assert pool.get_entry(transaction.txid()).fee_rate == 0


@pytest.mark.parametrize("malformed", [None, {}, [], 1, True, "transaction"])
def test_non_transactions_rejected_without_mutation(funding, malformed):
    pool = Mempool(funding[2], set())
    assert not pool.add_transaction(malformed)
    assert len(pool) == pool.total_bytes == 0
    assert pool.add_transaction(spend(funding))


@pytest.mark.parametrize(
    "field,value",
    [("inputs", None), ("inputs", [{}]), ("outputs", [None]), ("timestamp", True), ("version", 2)],
)
def test_malformed_fields_rejected_without_reserving_inputs(funding, field, value):
    pool = Mempool(funding[2], set())
    transaction = spend(funding)
    setattr(transaction, field, value)
    assert not pool.add_transaction(transaction)
    assert len(pool) == pool.total_bytes == 0
    assert pool.add_transaction(spend(funding))


def test_coinbase_unsigned_bad_signature_wrong_owner_and_overspend_rejected(funding):
    pool = Mempool(funding[2], set())
    assert not pool.add_transaction(
        create_coinbase_transaction(funding[1], timestamp=123)
    )
    unsigned = spend(funding)
    unsigned.inputs[0].signature = ""
    bad_signature = spend(funding)
    bad_signature.inputs[0].signature = "zz"
    wrong_owner = spend(funding)
    wrong_owner.sign_input(0, SigningKey.from_secret_exponent(2, curve=SECP256k1))
    overspend = spend(funding, amount=101)
    for transaction in (unsigned, bad_signature, wrong_owner, overspend):
        assert not pool.add_transaction(transaction)
        assert len(pool) == pool.total_bytes == 0
    assert pool.add_transaction(spend(funding))


def test_duplicate_and_first_seen_input_conflict_are_atomic(funding):
    pool = Mempool(funding[2], set())
    original = spend(funding)
    assert pool.add_transaction(original)
    before = state(pool)
    assert not pool.add_transaction(original)
    assert not pool.add_transaction(spend(funding, amount=50, timestamp=124))
    assert state(pool) == before
    assert pool.get_transaction(original.txid()) == original


def test_historical_txid_rejected_even_if_its_inputs_are_available(funding):
    transaction = spend(funding)
    pool = Mempool(funding[2], {transaction.txid()})
    assert not pool.add_transaction(transaction)
    assert len(pool) == pool.total_bytes == 0


def test_failed_multi_input_admission_does_not_reserve_valid_input(funding):
    transaction = Transaction(
        [TxInput("funding-a", 0), TxInput("unknown", 0)],
        [TxOutput(99, funding[1])],
        timestamp=123,
    )
    for index in range(2):
        transaction.sign_input(index, funding[0])
    pool = Mempool(funding[2], set())
    assert not pool.add_transaction(transaction)
    assert pool.add_transaction(spend(funding))


def test_later_input_already_pending_spent_does_not_reserve_first_input(funding):
    pool = Mempool(funding[2], set())
    existing = spend(funding, "funding-b")
    assert pool.add_transaction(existing)
    transaction = Transaction(
        [TxInput("funding-a", 0), TxInput("funding-b", 0)],
        [TxOutput(150, funding[1])],
        timestamp=123,
    )
    for index in range(2):
        transaction.sign_input(index, funding[0])
    before = state(pool)
    assert not pool.add_transaction(transaction)
    assert state(pool) == before
    assert pool.add_transaction(spend(funding))


def test_output_collision_rejected_without_reserving_inputs(funding):
    transaction = spend(funding)
    funding[2].add(transaction.txid(), 0, TxOutput(7, funding[1]))
    before = funding[2].to_dict()
    pool = Mempool(funding[2], set())
    assert not pool.add_transaction(transaction)
    assert len(pool) == pool.total_bytes == 0
    assert funding[2].to_dict() == before
    assert pool.add_transaction(spend(funding, amount=98, timestamp=124))


def test_parent_then_child_admission_and_orphan_rejection(funding):
    parent, child, grandchild, _ = family(funding)
    pool = Mempool(funding[2], set())
    assert not pool.add_transaction(child)
    assert not pool.add_transaction(grandchild)
    for transaction in (parent, child, grandchild):
        assert pool.add_transaction(transaction)
    assert ids(pool.get_transactions()) == ids([parent, child, grandchild])
    assert pool.get_entry(child.txid()).fee == 10


def test_pending_output_conflict_rejected_after_child_reserves_it(funding):
    parent, child, grandchild, _ = family(funding)
    pool = Mempool(funding[2], set())
    assert pool.add_transaction(parent)
    assert pool.add_transaction(child)
    before = state(pool)
    competitor = spend(funding, parent.txid(), 80, timestamp=124)
    assert not pool.add_transaction(competitor)
    assert state(pool) == before
    assert pool.add_transaction(grandchild)


def test_admission_does_not_mutate_confirmed_utxos(funding):
    pool = Mempool(funding[2], set())
    before = funding[2].to_dict()
    assert pool.add_transaction(spend(funding))
    assert funding[2].to_dict() == before


def test_count_capacity_releases_after_removal(funding):
    pool = Mempool(funding[2], set(), max_transactions=1)
    first, second = spend(funding), spend(funding, "funding-b")
    assert pool.add_transaction(first)
    before = state(pool)
    assert not pool.add_transaction(second)
    assert state(pool) == before
    assert pool.remove_transaction(first.txid())
    assert pool.add_transaction(second)


def test_exact_byte_capacity_and_overflow_leave_no_reservations(funding):
    first, second = spend(funding), spend(funding, "funding-b")
    size = len(serialize(first.to_dict()))
    pool = Mempool(funding[2], set(), max_bytes=size)
    assert pool.add_transaction(first)
    assert pool.total_bytes == size
    before = state(pool)
    assert not pool.add_transaction(second)
    assert state(pool) == before
    assert pool.remove_transaction(first.txid())
    assert pool.add_transaction(second)
    too_small = Mempool(funding[2], set(), max_bytes=size - 1)
    assert not too_small.add_transaction(first)
    assert len(too_small) == too_small.total_bytes == 0


def test_constructor_copies_external_state(funding):
    transaction = spend(funding)
    seen = set()
    pool = Mempool(funding[2], seen)
    funding[2].spend("funding-a", 0)
    seen.add(transaction.txid())
    assert pool.add_transaction(transaction)


def test_all_transaction_views_and_copy_are_independent(funding):
    transaction = spend(funding)
    txid = transaction.txid()
    expected = deepcopy(transaction)
    pool = Mempool(funding[2], set(), max_transactions=7, max_bytes=7000)
    assert pool.add_transaction(transaction)
    transaction.outputs[0].amount = 1
    pool.get_transaction(txid).inputs[0].signature = ""
    pool.get_entry(txid).transaction.outputs[0].amount = 1
    pool.get_transactions()[0].outputs.clear()
    pool.select_transactions()[0].inputs.clear()
    assert pool.get_transaction(txid) == expected
    snapshot = pool.copy()
    assert snapshot.max_transactions == 7
    assert snapshot.max_bytes == 7000
    assert state(snapshot) == state(pool)
    assert snapshot.remove_transaction(txid)
    assert pool.has_transaction(txid)
    assert snapshot.add_transaction(spend(funding, amount=90, timestamp=124))
    assert state(snapshot) != state(pool)


@pytest.mark.parametrize("missing", ["missing", None, [], {}])
def test_missing_lookup_and_removal_are_safe(funding, missing):
    pool = Mempool(funding[2], set())
    assert pool.add_transaction(spend(funding))
    before = state(pool)
    assert not pool.has_transaction(missing)
    assert pool.get_transaction(missing) is None
    assert pool.get_entry(missing) is None
    assert not pool.remove_transaction(missing)
    assert state(pool) == before


def test_remove_parent_cascades_descendants_and_releases_inputs(funding):
    parent, child, grandchild, unrelated = family(funding)
    pool = Mempool(funding[2], set())
    for transaction in (parent, child, grandchild, unrelated):
        assert pool.add_transaction(transaction)
    assert pool.remove_transaction(parent.txid())
    assert ids(pool.get_transactions()) == [unrelated.txid()]
    assert pool.total_bytes == len(serialize(unrelated.to_dict()))
    assert pool.add_transaction(spend(funding, amount=90, timestamp=124))


def test_remove_child_preserves_parent_and_allows_replacement_child(funding):
    parent, child, grandchild, unrelated = family(funding)
    pool = Mempool(funding[2], set())
    for transaction in (parent, child, grandchild, unrelated):
        assert pool.add_transaction(transaction)
    assert pool.remove_transaction(child.txid())
    assert ids(pool.get_transactions()) == ids([parent, unrelated])
    assert pool.add_transaction(spend(funding, parent.txid(), 90, timestamp=124))


def test_remove_child_preserves_sibling_spending_another_parent_output(funding):
    parent = spend(funding)
    parent.outputs = [TxOutput(50, funding[1]), TxOutput(49, funding[1])]
    parent.sign_input(0, funding[0])
    child = spend(funding, parent.txid(), 45)
    descendant = spend(funding, child.txid(), 40)
    sibling = Transaction(
        [TxInput(parent.txid(), 1)], [TxOutput(44, funding[1])], timestamp=123
    )
    sibling.sign_input(0, funding[0])
    pool = Mempool(funding[2], set())
    for transaction in (parent, child, descendant, sibling):
        assert pool.add_transaction(transaction)
    assert pool.remove_transaction(child.txid())
    assert ids(pool.get_transactions()) == ids([parent, sibling])
    assert pool.add_transaction(spend(funding, parent.txid(), 46, timestamp=124))
    competing_sibling = deepcopy(sibling)
    competing_sibling.outputs[0].amount = 43
    competing_sibling.sign_input(0, funding[0])
    assert not pool.add_transaction(competing_sibling)


def test_revalidate_confirmed_parent_preserves_unspent_child_and_old_pool(funding):
    parent, child, grandchild, unrelated = family(funding)
    pool = Mempool(funding[2], set(), max_transactions=8, max_bytes=8000)
    for transaction in (parent, child, grandchild, unrelated):
        assert pool.add_transaction(transaction)
    before = state(pool)
    confirmed = funding[2].copy()
    confirmed.apply_valid_transaction(parent)
    rebuilt = pool.revalidated(confirmed, {parent.txid()})
    assert state(pool) == before
    assert ids(rebuilt.get_transactions()) == ids([child, grandchild, unrelated])
    assert rebuilt.max_transactions == 8
    assert rebuilt.max_bytes == 8000
    assert rebuilt.total_bytes == sum(len(serialize(tx.to_dict())) for tx in [child, grandchild, unrelated])
    assert rebuilt.get_entry(child.txid()).fee == 10
    assert ids(rebuilt.select_transactions())[0] == child.txid()


def test_revalidate_conflicting_block_drops_parent_and_all_descendants(funding):
    parent, child, grandchild, unrelated = family(funding)
    pool = Mempool(funding[2], set())
    for transaction in (parent, child, grandchild, unrelated):
        assert pool.add_transaction(transaction)
    competitor = spend(funding, amount=90, timestamp=124)
    confirmed = funding[2].copy()
    confirmed.apply_valid_transaction(competitor)
    rebuilt = pool.revalidated(confirmed, {competitor.txid()})
    assert ids(rebuilt.get_transactions()) == [unrelated.txid()]
    assert len(pool) == 4


def test_revalidate_confirmed_parent_with_spent_output_drops_child(funding):
    parent, child, grandchild, unrelated = family(funding)
    pool = Mempool(funding[2], set())
    for transaction in (parent, child, grandchild, unrelated):
        assert pool.add_transaction(transaction)
    competitor = spend(funding, parent.txid(), 90, timestamp=124)
    confirmed = funding[2].copy()
    confirmed.apply_valid_transaction(parent)
    confirmed.apply_valid_transaction(competitor)
    rebuilt = pool.revalidated(confirmed, {parent.txid(), competitor.txid()})
    assert ids(rebuilt.get_transactions()) == [unrelated.txid()]


def test_selection_uses_fee_rate_not_absolute_fee(funding):
    large = spend(funding, amount=96)
    large.outputs = [TxOutput(1, funding[1]) for _ in range(96)]
    large.sign_input(0, funding[0])
    small = spend(funding, "funding-b", 98)
    pool = Mempool(funding[2], set())
    assert pool.add_transaction(large)
    assert pool.add_transaction(small)
    assert pool.get_entry(large.txid()).fee > pool.get_entry(small.txid()).fee
    assert ids(pool.select_transactions()) == ids([small, large])


def test_equal_fee_rate_tie_breaks_by_txid_independent_of_insertion(funding):
    transactions = [spend(funding, source) for source in ("funding-a", "funding-b", "funding-c")]
    expected = sorted(ids(transactions))
    pool = Mempool(funding[2], set())
    for transaction in sorted(transactions, key=lambda tx: tx.txid(), reverse=True):
        assert pool.add_transaction(transaction)
    assert len({pool.get_entry(txid).fee_rate for txid in expected}) == 1
    assert ids(pool.select_transactions()) == expected


def test_selection_waits_for_pending_parents_and_rechecks_unlocked_children(funding):
    parent, child, grandchild, unrelated = family(funding)
    pool = Mempool(funding[2], set())
    for transaction in (parent, child, grandchild, unrelated):
        assert pool.add_transaction(transaction)
    before = state(pool)
    assert ids(pool.select_transactions(max_transactions=2)) == ids([unrelated, parent])
    assert ids(pool.select_transactions()) == ids([unrelated, parent, child, grandchild])
    assert state(pool) == before
    assert ids(pool.select_transactions()) == ids(pool.select_transactions())


def test_selection_requires_all_pending_parents(funding):
    first = spend(funding, amount=99)
    second = spend(funding, "funding-b", 98)
    child = Transaction(
        [TxInput(first.txid(), 0), TxInput(second.txid(), 0)],
        [TxOutput(150, funding[1])],
        timestamp=123,
    )
    for index in range(2):
        child.sign_input(index, funding[0])
    pool = Mempool(funding[2], set())
    for transaction in (first, second, child):
        assert pool.add_transaction(transaction)
    assert ids(pool.select_transactions()) == ids([second, first, child])
    assert pool.remove_transaction(first.txid())
    assert ids(pool.get_transactions()) == [second.txid()]


def test_selection_skips_oversized_entry_and_blocks_its_descendants(funding):
    parent = spend(funding, amount=50)
    parent.outputs = [TxOutput(1, funding[1]) for _ in range(50)]
    parent.sign_input(0, funding[0])
    child = spend(funding, parent.txid(), 1)
    unrelated = spend(funding, "funding-b", 99)
    pool = Mempool(funding[2], set())
    for transaction in (parent, child, unrelated):
        assert pool.add_transaction(transaction)
    assert pool.get_entry(parent.txid()).fee_rate > pool.get_entry(unrelated.txid()).fee_rate
    budget = len(serialize(child.to_dict())) + len(serialize(unrelated.to_dict()))
    assert budget < pool.get_entry(parent.txid()).size_bytes
    assert ids(pool.select_transactions(max_bytes=budget)) == [unrelated.txid()]


def test_selection_exact_byte_bound_and_zero_limits(funding):
    pool = Mempool(funding[2], set())
    transaction = spend(funding)
    assert pool.add_transaction(transaction)
    size = pool.total_bytes
    assert ids(pool.select_transactions(max_bytes=size)) == [transaction.txid()]
    assert pool.select_transactions(max_bytes=size - 1) == []
    assert pool.select_transactions(max_bytes=0) == []
    assert pool.select_transactions(max_transactions=0) == []


def test_selection_enforces_sum_of_selected_transaction_bytes(funding):
    pool = Mempool(funding[2], set())
    transactions = [spend(funding, source) for source in ("funding-a", "funding-b", "funding-c")]
    for transaction in transactions:
        assert pool.add_transaction(transaction)
    size = len(serialize(transactions[0].to_dict()))
    selected = pool.select_transactions(max_bytes=size * 2)
    assert ids(selected) == sorted(ids(transactions))[:2]
    assert sum(len(serialize(tx.to_dict())) for tx in selected) == size * 2
    assert len(pool.select_transactions(max_bytes=size * 2 - 1)) == 1


@pytest.mark.parametrize("limit", [-1, True, False, 1.0, "1", None])
@pytest.mark.parametrize("name", ["max_transactions", "max_bytes"])
def test_selection_rejects_invalid_limits_even_when_empty(name, limit):
    with pytest.raises(ValueError, match=name):
        Mempool().select_transactions(**{name: limit})
