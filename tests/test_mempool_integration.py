from copy import deepcopy
from fractions import Fraction

import pytest
from ecdsa import SECP256k1, SigningKey

from blockchain.block import Block
from blockchain.blockchain import Blockchain
from blockchain.genesis import GENESIS_TIMESTAMP
from blockchain.validation import validate_block_header
from consensus.difficulty import MINING_DIFFICULTY
from consensus.pow import validate_proof_of_work
from crypto.address import public_key_to_address
from crypto.hash import serialize
from mining.coinbase import create_coinbase_transaction
from mining.miner import mine_block
from transaction.transaction import Transaction
from transaction.tx_input import TxInput
from transaction.tx_output import TxOutput


NOW = GENESIS_TIMESTAMP + 100
ALICE_KEY = SigningKey.from_secret_exponent(21, curve=SECP256k1)
BOB_KEY = SigningKey.from_secret_exponent(22, curve=SECP256k1)
CAROL_KEY = SigningKey.from_secret_exponent(23, curve=SECP256k1)
MINER_KEY = SigningKey.from_secret_exponent(24, curve=SECP256k1)
ALICE = public_key_to_address(ALICE_KEY.get_verifying_key())
BOB = public_key_to_address(BOB_KEY.get_verifying_key())
CAROL = public_key_to_address(CAROL_KEY.get_verifying_key())
MINER = public_key_to_address(MINER_KEY.get_verifying_key())
ADDRESSES = (ALICE, BOB, CAROL, MINER)


def mine(template: Block) -> Block:
    mined = mine_block(template, max_nonce=100_000)
    assert mined is not None
    return mined


def funded_chain(**configuration) -> tuple[Blockchain, Transaction]:
    chain = Blockchain(**configuration)
    block = mine(chain.create_block_template(ALICE, timestamp=GENESIS_TIMESTAMP + 1))
    assert chain.add_block(block, current_time=NOW)
    return chain, block.transactions[0]


def transfer(
    source: Transaction,
    private_key: SigningKey,
    outputs: list[tuple[int, str]],
    *,
    output_index: int = 0,
) -> Transaction:
    transaction = Transaction(
        inputs=[TxInput(source.txid(), output_index)],
        outputs=[TxOutput(amount, address) for amount, address in outputs],
        timestamp=GENESIS_TIMESTAMP + 10,
    )
    transaction.sign_input(0, private_key)
    return transaction


def template(chain: Blockchain, **limits) -> Block:
    return chain.create_mempool_block_template(
        MINER, timestamp=chain.get_latest_block().timestamp + 1, **limits
    )


def raw_candidate(
    chain: Blockchain, transactions: list[Transaction], *, reward: int = 50
) -> Block:
    """Build mined receive-side payloads, including invalid ledger contents."""
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


def split_chain(**configuration) -> tuple[Blockchain, Transaction]:
    chain, funding = funded_chain(**configuration)
    split = transfer(funding, ALICE_KEY, [(20, ALICE), (20, BOB), (9, CAROL)])
    assert chain.add_block(raw_candidate(chain, [split], reward=51), current_time=NOW)
    return chain, split


def pending_ids(chain: Blockchain) -> list[str]:
    return [transaction.txid() for transaction in chain.mempool.get_transactions()]


def snapshot(chain: Blockchain, *tracked_txids: str) -> tuple:
    pool = chain.mempool
    pending = pool.get_transactions()
    tracked = {
        transaction.txid()
        for block in chain.chain
        for transaction in block.transactions
    }
    tracked.update(transaction.txid() for transaction in pending)
    tracked.update(tracked_txids)
    entries = []
    for transaction in pending:
        entry = pool.get_entry(transaction.txid())
        assert entry is not None
        entries.append(
            (transaction.to_dict(), entry.fee, entry.size_bytes, entry.fee_rate)
        )
    return (
        [block.to_dict() for block in chain.chain],
        chain.utxo_set.to_dict(),
        {address: chain.get_balance(address) for address in ADDRESSES},
        {txid: chain.has_transaction(txid) for txid in tracked},
        entries,
        len(pool),
        pool.total_bytes,
    )


def test_submission_keeps_confirmed_state_and_exposes_verified_fee_metadata():
    chain, funding = funded_chain()
    transaction = transfer(funding, ALICE_KEY, [(30, BOB), (18, ALICE)])
    before = snapshot(chain, transaction.txid())

    assert chain.submit_transaction(transaction)
    assert snapshot(chain, transaction.txid())[:4] == before[:4]
    assert chain.get_balance(ALICE) == 50
    assert chain.get_balance(BOB) == 0
    assert not chain.has_transaction(transaction.txid())
    pool = chain.mempool
    assert pool.has_transaction(transaction.txid())
    entry = pool.get_entry(transaction.txid())
    size = len(serialize(transaction.to_dict()))
    assert entry is not None
    assert entry.fee == 2
    assert entry.size_bytes == size
    assert entry.fee_rate == Fraction(2, size)
    assert pool.total_bytes == size
    submitted = snapshot(chain, transaction.txid())
    assert not chain.submit_transaction(transaction)
    assert snapshot(chain, transaction.txid()) == submitted


def test_template_and_mining_leave_pool_unchanged_until_successful_append():
    chain, funding = funded_chain()
    transaction = transfer(funding, ALICE_KEY, [(47, BOB)])
    assert chain.submit_transaction(transaction)
    before = snapshot(chain)

    candidate = template(chain)
    assert candidate.transactions[0].outputs[0].amount == 53
    assert [tx.txid() for tx in candidate.transactions[1:]] == [transaction.txid()]
    mined = mine(candidate)
    assert snapshot(chain) == before
    assert chain.add_block(mined, current_time=NOW)
    assert chain.has_transaction(transaction.txid())
    assert chain.get_balance(ALICE) == 0
    assert chain.get_balance(BOB) == 47
    assert chain.get_balance(MINER) == 53
    assert len(chain.mempool) == 0
    assert chain.mempool.total_bytes == 0
    assert chain.validate_chain(current_time=NOW)


def test_selection_ranks_only_ready_transactions_and_keeps_parent_before_child():
    chain, split = split_chain()
    parent = transfer(split, ALICE_KEY, [(19, ALICE)])
    child = transfer(parent, ALICE_KEY, [(1, CAROL)])
    independent = transfer(split, BOB_KEY, [(15, CAROL)], output_index=1)
    for transaction in (parent, child, independent):
        assert chain.submit_transaction(transaction)
    before = snapshot(chain)

    expected = [independent.txid(), parent.txid(), child.txid()]
    for limit in (1, 2, 3):
        candidate = template(chain, max_transactions=limit)
        assert [tx.txid() for tx in candidate.transactions[1:]] == expected[:limit]
        assert candidate.transactions[0].outputs[0].amount == (55, 56, 74)[limit - 1]
    assert snapshot(chain) == before


def test_byte_limit_counts_serialized_regular_transactions_and_is_exact():
    chain, funding = funded_chain()
    parent = transfer(funding, ALICE_KEY, [(45, BOB)])
    child = transfer(parent, BOB_KEY, [(41, CAROL)])
    assert chain.submit_transaction(parent)
    assert chain.submit_transaction(child)
    parent_size = len(serialize(parent.to_dict()))
    child_size = len(serialize(child.to_dict()))

    assert len(template(chain, max_bytes=parent_size - 1).transactions) == 1
    exact_parent = template(chain, max_bytes=parent_size)
    assert [tx.txid() for tx in exact_parent.transactions[1:]] == [parent.txid()]
    exact_both = template(chain, max_bytes=parent_size + child_size)
    assert [tx.txid() for tx in exact_both.transactions[1:]] == [parent.txid(), child.txid()]
    assert exact_both.transactions[0].outputs[0].amount == 59
    assert len(chain.mempool) == 2


def test_partial_confirmation_preserves_child_and_revalidates_it_against_chain():
    chain, funding = funded_chain()
    parent = transfer(funding, ALICE_KEY, [(45, BOB)])
    child = transfer(parent, BOB_KEY, [(41, CAROL)])
    assert chain.submit_transaction(parent)
    assert chain.submit_transaction(child)
    child_entry = chain.mempool.get_entry(child.txid())

    assert chain.add_block(mine(template(chain, max_transactions=1)), current_time=NOW)
    assert chain.has_transaction(parent.txid())
    assert not chain.has_transaction(child.txid())
    assert pending_ids(chain) == [child.txid()]
    surviving_entry = chain.mempool.get_entry(child.txid())
    assert surviving_entry.fee == child_entry.fee == 4
    assert surviving_entry.size_bytes == child_entry.size_bytes
    assert surviving_entry.fee_rate == child_entry.fee_rate
    assert chain.get_balance(BOB) == 45

    candidate = template(chain)
    assert [tx.txid() for tx in candidate.transactions[1:]] == [child.txid()]
    assert candidate.transactions[0].outputs[0].amount == 54
    assert chain.add_block(mine(candidate), current_time=NOW)
    assert len(chain.mempool) == 0
    assert chain.get_balance(BOB) == 0
    assert chain.get_balance(CAROL) == 41


def test_external_conflict_removes_pending_branch_and_retains_unrelated_transaction():
    chain, split = split_chain()
    parent = transfer(split, ALICE_KEY, [(19, ALICE)])
    child = transfer(parent, ALICE_KEY, [(18, BOB)])
    grandchild = transfer(child, BOB_KEY, [(17, CAROL)])
    independent = transfer(split, BOB_KEY, [(15, CAROL)], output_index=1)
    for transaction in (parent, child, grandchild, independent):
        assert chain.submit_transaction(transaction)
    competing = transfer(split, ALICE_KEY, [(16, CAROL)])

    assert chain.add_block(raw_candidate(chain, [competing], reward=54), current_time=NOW)
    assert pending_ids(chain) == [independent.txid()]
    assert chain.mempool.total_bytes == len(serialize(independent.to_dict()))
    for transaction in (parent, child, grandchild):
        assert not chain.has_transaction(transaction.txid())
        assert not chain.mempool.has_transaction(transaction.txid())
    assert chain.has_transaction(competing.txid())
    assert chain.get_balance(CAROL) == 25
    assert [tx.txid() for tx in template(chain).transactions[1:]] == [independent.txid()]


def test_valid_block_can_confirm_unpooled_transactions_while_pool_is_nonempty():
    chain, split = split_chain()
    pending = transfer(split, ALICE_KEY, [(19, CAROL)])
    external = transfer(split, BOB_KEY, [(16, CAROL)], output_index=1)
    assert chain.submit_transaction(pending)

    assert chain.add_block(raw_candidate(chain, [external], reward=54), current_time=NOW)
    assert chain.has_transaction(external.txid())
    assert pending_ids(chain) == [pending.txid()]
    assert not chain.has_transaction(pending.txid())
    assert chain.get_balance(ALICE) == 20
    assert chain.get_balance(BOB) == 0
    assert chain.get_balance(CAROL) == 25


@pytest.mark.parametrize("defect", ["invalid_suffix", "reward_overclaim", "invalid_pow"])
def test_rejected_blocks_preserve_exact_chain_utxos_pool_fees_and_bytes(defect):
    chain, funding = funded_chain()
    parent = transfer(funding, ALICE_KEY, [(45, BOB)])
    child = transfer(parent, BOB_KEY, [(40, CAROL)])
    assert chain.submit_transaction(parent)
    assert chain.submit_transaction(child)
    if defect == "invalid_suffix":
        invalid = transfer(child, CAROL_KEY, [(41, ALICE)])
        candidate = raw_candidate(chain, [parent, child, invalid], reward=60)
    elif defect == "reward_overclaim":
        candidate = raw_candidate(chain, [parent, child], reward=61)
    else:
        candidate = raw_candidate(chain, [parent, child], reward=60)
        while validate_proof_of_work(candidate):
            candidate.nonce += 1
    if defect != "invalid_pow":
        assert validate_block_header(candidate, chain.get_latest_block(), current_time=NOW)
    tracked = tuple(transaction.txid() for transaction in candidate.transactions)
    before = snapshot(chain, *tracked)

    assert not chain.add_block(candidate, current_time=NOW)
    assert snapshot(chain, *tracked) == before
    assert chain.add_block(mine(template(chain)), current_time=NOW)
    assert len(chain.mempool) == 0
    assert chain.get_balance(CAROL) == 40


def test_submitted_objects_and_public_pool_snapshots_cannot_mutate_live_pool():
    chain, funding = funded_chain()
    transaction = transfer(funding, ALICE_KEY, [(45, BOB)])
    txid = transaction.txid()
    assert chain.submit_transaction(transaction)
    before = snapshot(chain)

    transaction.outputs[0].amount = 999
    detached_pool = chain.mempool
    detached_pool.get_transaction(txid).outputs[0].amount = 888
    detached_entry = detached_pool.get_entry(txid)
    assert detached_entry is not None
    detached_entry.transaction.outputs[0].amount = 666
    # Even forcibly changing frozen metadata on an exported entry cannot
    # inflate the reward calculated from the owning chain's actual UTXOs.
    object.__setattr__(detached_entry, "fee", 1_000_000)
    transactions = detached_pool.get_transactions()
    transactions[0].inputs[0].signature = "00" * 64
    transactions.clear()
    assert detached_pool.remove_transaction(txid)
    assert len(detached_pool) == 0
    chain.create_mempool_block_template(
        MINER, timestamp=GENESIS_TIMESTAMP + 2
    ).transactions[1].outputs[0].amount = 777

    assert snapshot(chain) == before
    candidate = template(chain)
    assert candidate.transactions[1].txid() == txid
    assert candidate.transactions[0].outputs[0].amount == 55
    assert chain.add_block(mine(candidate), current_time=NOW)
    assert chain.get_balance(BOB) == 45


def test_explicit_pending_removal_cascades_but_does_not_change_confirmed_state():
    chain, split = split_chain()
    parent = transfer(split, ALICE_KEY, [(19, ALICE)])
    child = transfer(parent, ALICE_KEY, [(18, BOB)])
    independent = transfer(split, BOB_KEY, [(15, CAROL)], output_index=1)
    for transaction in (parent, child, independent):
        assert chain.submit_transaction(transaction)
    before = snapshot(chain)

    assert chain.remove_pending_transaction(parent.txid())
    assert snapshot(chain, parent.txid(), child.txid())[:4] == before[:4]
    assert pending_ids(chain) == [independent.txid()]
    assert chain.mempool.total_bytes == len(serialize(independent.to_dict()))
    remaining = snapshot(chain)
    assert not chain.remove_pending_transaction(parent.txid())
    assert not chain.remove_pending_transaction("f" * 64)
    assert snapshot(chain) == remaining


def test_full_pool_does_not_veto_blocks_and_confirmation_releases_capacity():
    chain, split = split_chain(mempool_max_transactions=1)
    pending = transfer(split, ALICE_KEY, [(19, ALICE)])
    external = transfer(split, BOB_KEY, [(16, CAROL)], output_index=1)
    assert chain.submit_transaction(pending)
    before = snapshot(chain, external.txid())
    assert not chain.submit_transaction(external)
    assert snapshot(chain, external.txid()) == before

    assert chain.add_block(raw_candidate(chain, [external], reward=54), current_time=NOW)
    assert pending_ids(chain) == [pending.txid()]
    assert chain.add_block(mine(template(chain)), current_time=NOW)
    child = transfer(pending, ALICE_KEY, [(18, BOB)])
    assert chain.submit_transaction(child)
    assert pending_ids(chain) == [child.txid()]


def test_byte_capacity_is_local_policy_and_never_a_block_consensus_limit():
    chain, funding = funded_chain(mempool_max_bytes=1)
    external = transfer(funding, ALICE_KEY, [(45, BOB)])
    before = snapshot(chain, external.txid())

    assert not chain.submit_transaction(external)
    assert snapshot(chain, external.txid()) == before
    assert chain.add_block(raw_candidate(chain, [external], reward=55), current_time=NOW)
    assert chain.has_transaction(external.txid())
    assert chain.get_balance(BOB) == 45
    assert len(chain.mempool) == 0


@pytest.mark.parametrize(
    "configuration",
    [
        {"mempool_max_transactions": -1},
        {"mempool_max_bytes": -1},
        {"mempool_max_transactions": True},
        {"mempool_max_bytes": 1.5},
    ],
)
def test_blockchain_forwards_and_validates_pool_configuration(configuration):
    with pytest.raises((TypeError, ValueError)):
        Blockchain(**configuration)


def test_existing_template_api_remains_coinbase_only_or_uses_explicit_transactions():
    chain, funding = funded_chain()
    pending = transfer(funding, ALICE_KEY, [(45, BOB)])
    assert chain.submit_transaction(pending)
    before = snapshot(chain)

    coinbase_only = chain.create_block_template(MINER, timestamp=GENESIS_TIMESTAMP + 2)
    assert len(coinbase_only.transactions) == 1
    assert coinbase_only.transactions[0].outputs[0].amount == 50
    external = transfer(funding, ALICE_KEY, [(44, CAROL)])
    explicit = chain.create_block_template(
        MINER, transactions=[external], timestamp=GENESIS_TIMESTAMP + 2
    )
    assert [tx.txid() for tx in explicit.transactions[1:]] == [external.txid()]
    assert explicit.transactions[0].outputs[0].amount == 56
    assert snapshot(chain) == before
    assert chain.add_block(mine(explicit), current_time=NOW)
    assert len(chain.mempool) == 0
    assert chain.get_balance(CAROL) == 44


@pytest.mark.parametrize("defect", ["conflict", "bad_signature", "unknown_input", "coinbase"])
def test_rejected_submission_does_not_damage_an_existing_pending_branch(defect):
    chain, funding = funded_chain()
    parent = transfer(funding, ALICE_KEY, [(45, BOB)])
    child = transfer(parent, BOB_KEY, [(40, CAROL)])
    assert chain.submit_transaction(parent)
    assert chain.submit_transaction(child)
    invalid = transfer(child, CAROL_KEY, [(39, ALICE)])
    if defect == "conflict":
        invalid = transfer(funding, ALICE_KEY, [(44, CAROL)])
    elif defect == "bad_signature":
        invalid.inputs[0].signature = "00" * 64
    elif defect == "unknown_input":
        invalid.inputs[0].previous_tx_id = "f" * 64
        invalid.sign_input(0, CAROL_KEY)
    else:
        invalid = create_coinbase_transaction(MINER, timestamp=GENESIS_TIMESTAMP + 2)
    before = snapshot(chain, invalid.txid())

    assert not chain.submit_transaction(invalid)
    assert snapshot(chain, invalid.txid()) == before
    assert chain.add_block(mine(template(chain)), current_time=NOW)
    assert chain.get_balance(CAROL) == 40


def test_empty_template_budgets_leave_all_pending_transactions_available():
    chain, funding = funded_chain()
    pending = transfer(funding, ALICE_KEY, [(45, BOB)])
    assert chain.submit_transaction(pending)
    before = snapshot(chain)

    for limits in ({"max_transactions": 0}, {"max_bytes": 0}):
        candidate = template(chain, **limits)
        assert len(candidate.transactions) == 1
        assert candidate.transactions[0].outputs[0].amount == 50
    assert snapshot(chain) == before
    assert len(template(chain).transactions) == 2


def test_distinct_chains_have_independent_pending_pools():
    first, funding = funded_chain()
    second, second_funding = funded_chain()
    assert funding.txid() == second_funding.txid()
    pending = transfer(funding, ALICE_KEY, [(45, BOB)])

    assert first.submit_transaction(pending)
    assert len(first.mempool) == 1
    assert len(second.mempool) == 0
    assert second.submit_transaction(pending)
    assert first.remove_pending_transaction(pending.txid())
    assert len(first.mempool) == 0
    assert pending_ids(second) == [pending.txid()]


def test_stale_mined_template_cannot_remove_pool_entries_after_tip_advances():
    chain, funding = funded_chain()
    pending = transfer(funding, ALICE_KEY, [(45, BOB)])
    assert chain.submit_transaction(pending)
    stale = mine(template(chain))
    coinbase_only = chain.create_block_template(
        MINER, timestamp=GENESIS_TIMESTAMP + 2
    )
    assert chain.add_block(mine(coinbase_only), current_time=NOW)
    assert pending_ids(chain) == [pending.txid()]
    tracked = tuple(transaction.txid() for transaction in stale.transactions)
    before = snapshot(chain, *tracked)

    assert not chain.add_block(stale, current_time=NOW)
    assert snapshot(chain, *tracked) == before
    assert chain.add_block(mine(template(chain)), current_time=NOW)
    assert len(chain.mempool) == 0
    assert chain.has_transaction(pending.txid())
    assert chain.get_balance(BOB) == 45
    assert chain.validate_chain(current_time=NOW)


def test_pool_revalidation_failure_cannot_partially_commit_a_valid_block(monkeypatch):
    chain, funding = funded_chain()
    pending = transfer(funding, ALICE_KEY, [(45, BOB)])
    assert chain.submit_transaction(pending)
    candidate = mine(template(chain))
    tracked = tuple(transaction.txid() for transaction in candidate.transactions)
    before = snapshot(chain, *tracked)

    def fail_revalidation(pool, utxo_set, seen_txids):
        # The candidate ledger has advanced, while the owning chain must not
        # publish any of it until the replacement pool is also ready.
        assert utxo_set.get_balance(BOB) == 45
        assert pending.txid() in seen_txids
        assert chain.get_balance(ALICE) == 50
        assert not chain.has_transaction(pending.txid())
        raise RuntimeError("injected pool rebuild failure")

    with monkeypatch.context() as patch:
        patch.setattr("transaction.mempool.Mempool.revalidated", fail_revalidation)
        with pytest.raises(RuntimeError, match="injected pool rebuild failure"):
            chain.add_block(candidate, current_time=NOW)
    assert snapshot(chain, *tracked) == before

    assert chain.add_block(candidate, current_time=NOW)
    assert chain.has_transaction(pending.txid())
    assert chain.get_balance(BOB) == 45
    assert chain.get_balance(MINER) == 55
    assert len(chain.mempool) == 0
    assert chain.validate_chain(current_time=NOW)


def test_multi_parent_child_survives_when_only_one_parent_is_confirmed():
    chain, split = split_chain()
    first = transfer(split, ALICE_KEY, [(18, ALICE)])
    second = transfer(split, BOB_KEY, [(17, BOB)], output_index=1)
    child = Transaction(
        inputs=[TxInput(first.txid(), 0), TxInput(second.txid(), 0)],
        outputs=[TxOutput(34, CAROL)],
        timestamp=GENESIS_TIMESTAMP + 11,
    )
    child.sign_input(0, ALICE_KEY)
    child.sign_input(1, BOB_KEY)
    for transaction in (first, second, child):
        assert chain.submit_transaction(transaction)
    child_entry = chain.mempool.get_entry(child.txid())

    assert chain.add_block(raw_candidate(chain, [first], reward=52), current_time=NOW)
    assert pending_ids(chain) == [second.txid(), child.txid()]
    assert chain.has_transaction(first.txid())
    assert not chain.has_transaction(second.txid())
    assert not chain.has_transaction(child.txid())
    surviving_entry = chain.mempool.get_entry(child.txid())
    assert surviving_entry.fee == child_entry.fee == 1
    assert surviving_entry.size_bytes == child_entry.size_bytes
    assert surviving_entry.fee_rate == child_entry.fee_rate
    assert [tx.txid() for tx in template(chain, max_transactions=1).transactions[1:]] == [
        second.txid()
    ]

    candidate = template(chain)
    assert [tx.txid() for tx in candidate.transactions[1:]] == [second.txid(), child.txid()]
    assert candidate.transactions[0].outputs[0].amount == 54
    assert chain.add_block(mine(candidate), current_time=NOW)
    assert chain.get_balance(ALICE) == 0
    assert chain.get_balance(BOB) == 0
    assert chain.get_balance(CAROL) == 43
    assert len(chain.mempool) == 0
    assert chain.validate_chain(current_time=NOW)
