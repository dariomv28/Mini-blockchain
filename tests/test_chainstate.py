from copy import deepcopy

import pytest
from ecdsa import SECP256k1, SigningKey

from blockchain.block import Block
from blockchain.blockchain import Blockchain
from blockchain.genesis import GENESIS_TIMESTAMP
from blockchain.validation import (
    rebuild_chain_state,
    validate_block,
    validate_block_header,
    validate_chain,
)
from consensus.difficulty import MINING_DIFFICULTY
from crypto.address import public_key_to_address
from mining.block_template import create_block_template
from mining.coinbase import create_coinbase_transaction
from mining.miner import mine_block
from transaction.transaction import Transaction
from transaction.tx_input import TxInput
from transaction.tx_output import TxOutput


NOW = GENESIS_TIMESTAMP + 100
ALICE_KEY = SigningKey.from_secret_exponent(11, curve=SECP256k1)
BOB_KEY = SigningKey.from_secret_exponent(12, curve=SECP256k1)
CAROL_KEY = SigningKey.from_secret_exponent(13, curve=SECP256k1)
MINER_KEY = SigningKey.from_secret_exponent(14, curve=SECP256k1)
ALICE = public_key_to_address(ALICE_KEY.get_verifying_key())
BOB = public_key_to_address(BOB_KEY.get_verifying_key())
CAROL = public_key_to_address(CAROL_KEY.get_verifying_key())
MINER = public_key_to_address(MINER_KEY.get_verifying_key())
ADDRESSES = (ALICE, BOB, CAROL, MINER)


def mine(template: Block) -> Block:
    mined = mine_block(template, max_nonce=100_000)
    assert mined is not None
    return mined


def funded_chain() -> tuple[Blockchain, Transaction]:
    chain = Blockchain()
    funding_block = mine(
        chain.create_block_template(ALICE, timestamp=GENESIS_TIMESTAMP + 1)
    )
    assert chain.add_block(funding_block, current_time=NOW)
    return chain, funding_block.transactions[0]


def transfer(
    source: Transaction,
    private_key: SigningKey,
    outputs: list[tuple[int, str]],
) -> Transaction:
    transaction = Transaction(
        inputs=[TxInput(source.txid(), 0)],
        outputs=[TxOutput(amount, address) for amount, address in outputs],
        timestamp=GENESIS_TIMESTAMP + 10,
    )
    transaction.sign_input(0, private_key)
    return transaction


def raw_candidate(
    chain: Blockchain,
    transactions: list[Transaction] | None = None,
    *,
    reward: int = 50,
    timestamp: int | None = None,
    coinbase: Transaction | None = None,
) -> Block:
    """Mine even invalid ledger payloads so rejection exercises state rules."""
    parent = chain.get_latest_block()
    block_timestamp = parent.timestamp + 1 if timestamp is None else timestamp
    if coinbase is None:
        coinbase = create_coinbase_transaction(MINER, timestamp=block_timestamp)
        coinbase.outputs[0].amount = reward
    return mine(
        Block(
            transactions=deepcopy([coinbase, *(transactions or [])]),
            previous_block_hash=parent.hash(),
            timestamp=block_timestamp,
            difficulty=MINING_DIFFICULTY,
        )
    )


def snapshot(chain: Blockchain, *extra_txids: str) -> tuple:
    txids = {
        transaction.txid()
        for block in chain.chain
        for transaction in block.transactions
    }
    txids.update(extra_txids)
    return (
        [block.to_dict() for block in chain.chain],
        {address: chain.get_balance(address) for address in ADDRESSES},
        {address: chain.get_utxos_for_address(address) for address in ADDRESSES},
        {txid: chain.has_transaction(txid) for txid in txids},
    )


def test_genesis_has_no_spendable_outputs_or_issued_coins():
    chain = Blockchain()
    state = rebuild_chain_state(chain.chain, current_time=NOW)

    assert state is not None
    assert state.seen_txids == set()
    assert chain.height == 0
    for address in ADDRESSES:
        assert chain.get_balance(address) == 0
        assert chain.get_utxos_for_address(address) == {}
        assert state.utxo_set.get_balance(address) == 0


def test_signed_transfer_pays_change_and_verified_fees_to_the_miner():
    chain, funding = funded_chain()
    transaction = transfer(funding, ALICE_KEY, [(30, BOB), (18, ALICE)])
    template = chain.create_block_template(
        MINER, transactions=[transaction], timestamp=GENESIS_TIMESTAMP + 2
    )

    assert template.transactions[0].outputs[0].amount == 52
    assert chain.add_block(mine(template), current_time=NOW)
    assert chain.get_balance(ALICE) == 18
    assert chain.get_balance(BOB) == 30
    assert chain.get_balance(MINER) == 52
    assert sum(chain.get_balance(address) for address in ADDRESSES) == 100
    assert not chain.utxo_set.exists(funding.txid(), 0)
    assert chain.has_transaction(funding.txid())
    assert chain.has_transaction(transaction.txid())
    assert chain.get_utxos_for_address(BOB) == {
        (transaction.txid(), 0): TxOutput(30, BOB)
    }
    assert chain.validate_chain(current_time=NOW)


def test_same_block_dependencies_are_applied_in_transaction_order():
    chain, funding = funded_chain()
    first = transfer(funding, ALICE_KEY, [(45, BOB)])
    second = transfer(first, BOB_KEY, [(40, CAROL)])
    template = chain.create_block_template(
        MINER, transactions=[first, second], timestamp=GENESIS_TIMESTAMP + 2
    )

    assert template.transactions[0].outputs[0].amount == 60
    assert chain.add_block(mine(template), current_time=NOW)
    assert chain.get_balance(ALICE) == 0
    assert chain.get_balance(BOB) == 0
    assert chain.get_balance(CAROL) == 40
    assert chain.get_balance(MINER) == 60
    assert not chain.utxo_set.exists(first.txid(), 0)
    assert chain.has_transaction(first.txid())
    assert chain.has_transaction(second.txid())


def test_transaction_can_combine_inputs_signed_by_different_owners():
    chain, funding = funded_chain()
    split = transfer(funding, ALICE_KEY, [(25, BOB), (24, ALICE)])
    assert chain.add_block(raw_candidate(chain, [split], reward=51), current_time=NOW)
    combined = Transaction(
        inputs=[TxInput(split.txid(), 0), TxInput(split.txid(), 1)],
        outputs=[TxOutput(48, CAROL)],
        timestamp=GENESIS_TIMESTAMP + 20,
    )
    combined.sign_input(0, BOB_KEY)
    combined.sign_input(1, ALICE_KEY)
    template = chain.create_block_template(
        MINER, transactions=[combined], timestamp=GENESIS_TIMESTAMP + 3
    )
    assert template.transactions[0].outputs[0].amount == 51
    assert chain.add_block(mine(template), current_time=template.timestamp)
    assert chain.get_balance(ALICE) == 0
    assert chain.get_balance(BOB) == 0
    assert chain.get_balance(CAROL) == 48
    assert chain.get_balance(MINER) == 102
    assert chain.validate_chain(current_time=template.timestamp)


def test_forward_reference_to_a_later_transaction_rejects_the_block():
    chain, funding = funded_chain()
    first = transfer(funding, ALICE_KEY, [(45, BOB)])
    second = transfer(first, BOB_KEY, [(40, CAROL)])
    candidate = raw_candidate(chain, [second, first])
    before = snapshot(chain, first.txid(), second.txid())

    assert validate_block_header(candidate, chain.get_latest_block(), current_time=NOW)
    assert not chain.add_block(candidate, current_time=NOW)
    assert snapshot(chain, first.txid(), second.txid()) == before
    with pytest.raises(ValueError):
        chain.create_block_template(MINER, transactions=[second, first])


def test_current_block_coinbase_cannot_fund_a_regular_transaction():
    chain = Blockchain()
    timestamp = GENESIS_TIMESTAMP + 1
    coinbase = create_coinbase_transaction(ALICE, timestamp=timestamp)
    transaction = transfer(coinbase, ALICE_KEY, [(49, BOB)])
    candidate = raw_candidate(
        chain, [transaction], timestamp=timestamp, coinbase=coinbase
    )
    before = snapshot(chain, coinbase.txid(), transaction.txid())

    assert validate_block_header(candidate, chain.get_latest_block(), current_time=NOW)
    assert not chain.add_block(candidate, current_time=NOW)
    assert snapshot(chain, coinbase.txid(), transaction.txid()) == before


def test_two_distinct_transactions_cannot_spend_the_same_outpoint_in_a_block():
    chain, funding = funded_chain()
    first = transfer(funding, ALICE_KEY, [(40, BOB)])
    second = transfer(funding, ALICE_KEY, [(39, CAROL)])
    assert first.txid() != second.txid()
    candidate = raw_candidate(chain, [first, second])
    before = snapshot(chain, first.txid(), second.txid())

    assert not chain.add_block(candidate, current_time=NOW)
    assert snapshot(chain, first.txid(), second.txid()) == before


def test_spent_outpoint_cannot_be_spent_again_in_a_later_block():
    chain, funding = funded_chain()
    first = transfer(funding, ALICE_KEY, [(40, BOB)])
    assert chain.add_block(raw_candidate(chain, [first]), current_time=NOW)
    second = transfer(funding, ALICE_KEY, [(39, CAROL)])
    candidate = raw_candidate(chain, [second])
    before = snapshot(chain, second.txid())

    assert not chain.add_block(candidate, current_time=NOW)
    assert snapshot(chain, second.txid()) == before
    assert chain.get_balance(BOB) == 40


def test_invalid_suffix_rolls_back_valid_prefix_and_allows_a_valid_retry():
    chain, funding = funded_chain()
    first = transfer(funding, ALICE_KEY, [(40, BOB)])
    invalid = transfer(first, BOB_KEY, [(39, CAROL)])
    invalid.inputs[0].previous_tx_id = "f" * 64
    invalid.sign_input(0, BOB_KEY)
    candidate = raw_candidate(chain, [first, invalid])
    tracked = (first.txid(), invalid.txid(), candidate.transactions[0].txid())
    before = snapshot(chain, *tracked)

    assert not chain.add_block(candidate, current_time=NOW)
    assert snapshot(chain, *tracked) == before
    assert chain.add_block(raw_candidate(chain, [first]), current_time=NOW)
    assert chain.has_transaction(first.txid())
    assert not chain.has_transaction(invalid.txid())
    assert chain.get_balance(BOB) == 40


@pytest.mark.parametrize("defect", ["wrong_owner", "bad_signature", "inflation", "duplicate_input"])
def test_invalid_signed_transactions_are_rejected_without_committing(defect):
    chain, funding = funded_chain()
    transaction = transfer(funding, ALICE_KEY, [(49, BOB)])
    if defect == "wrong_owner":
        transaction.sign_input(0, BOB_KEY)
    elif defect == "bad_signature":
        transaction.inputs[0].signature = "00" * 64
    elif defect == "inflation":
        transaction.outputs[0].amount = 51
        transaction.sign_input(0, ALICE_KEY)
    else:
        transaction.inputs.append(deepcopy(transaction.inputs[0]))
        transaction.sign_input(0, ALICE_KEY)
        transaction.sign_input(1, ALICE_KEY)
    candidate = raw_candidate(chain, [transaction])
    before = snapshot(chain, transaction.txid())

    assert validate_block_header(candidate, chain.get_latest_block(), current_time=NOW)
    assert not chain.add_block(candidate, current_time=NOW)
    assert snapshot(chain, transaction.txid()) == before


@pytest.mark.parametrize("output_index", [False, 0.0])
def test_non_integer_outpoint_index_cannot_alias_integer_zero(output_index):
    chain, funding = funded_chain()
    transaction = transfer(funding, ALICE_KEY, [(49, BOB)])
    transaction.inputs[0].output_index = output_index
    transaction.sign_input(0, ALICE_KEY)
    candidate = raw_candidate(chain, [transaction])
    before = snapshot(chain, transaction.txid())

    assert not chain.add_block(candidate, current_time=NOW)
    assert snapshot(chain, transaction.txid()) == before


def test_coinbase_overclaim_rolls_back_an_otherwise_valid_transfer():
    chain, funding = funded_chain()
    transaction = transfer(funding, ALICE_KEY, [(48, BOB)])
    candidate = raw_candidate(chain, [transaction], reward=53)
    before = snapshot(chain, transaction.txid(), candidate.transactions[0].txid())

    assert validate_block_header(candidate, chain.get_latest_block(), current_time=NOW)
    assert not chain.add_block(candidate, current_time=NOW)
    assert snapshot(chain, transaction.txid(), candidate.transactions[0].txid()) == before


@pytest.mark.parametrize("reward", [1, 51])
def test_miner_may_claim_less_than_subsidy_plus_fees(reward):
    chain, funding = funded_chain()
    transaction = transfer(funding, ALICE_KEY, [(48, BOB)])

    assert chain.add_block(
        raw_candidate(chain, [transaction], reward=reward), current_time=NOW
    )
    assert chain.get_balance(BOB) == 48
    assert chain.get_balance(MINER) == reward
    assert chain.validate_chain(current_time=NOW)


@pytest.mark.parametrize("spend_original", [False, True])
def test_historical_coinbase_txid_cannot_be_reissued_even_after_it_was_spent(spend_original):
    chain, funding = funded_chain()
    timestamp = chain.get_latest_block().timestamp
    if spend_original:
        transaction = transfer(funding, ALICE_KEY, [(50, BOB)])
        assert chain.add_block(
            raw_candidate(chain, [transaction], timestamp=timestamp), current_time=NOW
        )
        assert not chain.utxo_set.exists(funding.txid(), 0)
    else:
        assert chain.utxo_set.exists(funding.txid(), 0)
    replay = raw_candidate(chain, timestamp=timestamp, coinbase=funding)
    before = snapshot(chain)

    assert chain.has_transaction(funding.txid())
    assert validate_block_header(replay, chain.get_latest_block(), current_time=NOW)
    assert not chain.add_block(replay, current_time=NOW)
    assert snapshot(chain) == before
    assert not validate_chain([*chain.chain, replay], current_time=NOW)


def test_template_calculates_fees_without_spending_live_utxos():
    chain, funding = funded_chain()
    transaction = transfer(funding, ALICE_KEY, [(47, BOB)])
    before = snapshot(chain, transaction.txid())
    template = chain.create_block_template(
        MINER, transactions=[transaction], timestamp=GENESIS_TIMESTAMP + 2
    )

    assert template.transactions[0].outputs[0].amount == 53
    assert snapshot(chain, transaction.txid()) == before
    template.transactions[1].outputs[0].amount = 999
    assert transaction.outputs[0].amount == 47
    assert snapshot(chain, transaction.txid()) == before


def test_low_level_template_requires_complete_state_for_regular_transactions():
    chain, funding = funded_chain()
    transaction = transfer(funding, ALICE_KEY, [(47, BOB)])
    for state_arguments in ({}, {"utxo_set": chain.utxo_set}, {"seen_txids": {funding.txid()}}):
        with pytest.raises((TypeError, ValueError)):
            create_block_template(
                chain.get_latest_block(),
                MINER,
                transactions=[transaction],
                timestamp=GENESIS_TIMESTAMP + 2,
                **state_arguments,
            )
    template = create_block_template(
        chain.get_latest_block(), MINER, timestamp=GENESIS_TIMESTAMP + 2
    )
    assert template.transactions[0].outputs[0].amount == 50


def test_full_validator_uses_supplied_state_without_mutating_it():
    chain, funding = funded_chain()
    transaction = transfer(funding, ALICE_KEY, [(48, BOB)])
    candidate = raw_candidate(chain, [transaction], reward=52)
    state = rebuild_chain_state(chain.chain, current_time=NOW)
    assert state is not None
    seen_before = state.seen_txids.copy()

    assert validate_block(candidate, chain.get_latest_block(), state=state, current_time=NOW)
    assert state.seen_txids == seen_before
    assert state.utxo_set.get_balance(ALICE) == 50
    assert state.utxo_set.get_balance(BOB) == 0
    assert state.utxo_set.exists(funding.txid(), 0)


def test_replay_reconstructs_utxos_and_all_historical_transaction_ids():
    chain, funding = funded_chain()
    first = transfer(funding, ALICE_KEY, [(45, BOB)])
    second = transfer(first, BOB_KEY, [(40, CAROL)])
    assert chain.add_block(
        raw_candidate(chain, [first, second], reward=60), current_time=NOW
    )
    state = rebuild_chain_state(chain.chain, current_time=NOW)

    assert state is not None
    assert state.seen_txids == {
        transaction.txid()
        for block in chain.chain
        for transaction in block.transactions
    }
    for address in ADDRESSES:
        assert state.utxo_set.get_balance(address) == chain.get_balance(address)
        for outpoint, output in chain.get_utxos_for_address(address).items():
            assert state.utxo_set.get(*outpoint) == output
    assert not state.utxo_set.exists(funding.txid(), 0)
    assert not state.utxo_set.exists(first.txid(), 0)
    assert state.utxo_set.exists(second.txid(), 0)
    state.utxo_set.spend(second.txid(), 0)
    state.seen_txids.clear()
    assert chain.get_balance(CAROL) == 40
    assert chain.has_transaction(funding.txid())


def test_replay_rejects_valid_pow_history_with_invalid_ledger_transactions():
    chain, funding = funded_chain()
    transaction = transfer(funding, ALICE_KEY, [(51, BOB)])
    candidate = raw_candidate(chain, [transaction])
    history = [*chain.chain, candidate]

    assert validate_block_header(candidate, chain.get_latest_block(), current_time=NOW)
    assert not validate_chain(history, current_time=NOW)
    assert rebuild_chain_state(history, current_time=NOW) is None
    assert chain.validate_chain(current_time=NOW)


def test_public_block_and_utxo_snapshots_cannot_mutate_live_chainstate():
    chain, funding = funded_chain()
    transaction = transfer(funding, ALICE_KEY, [(48, BOB)])
    candidate = raw_candidate(chain, [transaction], reward=52)
    assert chain.add_block(candidate, current_time=NOW)
    expected = snapshot(chain)

    candidate.transactions[1].outputs[0].amount = 999
    transaction.outputs[0].amount = 888
    blocks = chain.chain
    blocks[-1].transactions[1].outputs[0].amount = 777
    chain.get_latest_block().transactions[0].outputs[0].amount = 666

    detached_utxos = chain.utxo_set
    outpoint = next(iter(chain.get_utxos_for_address(BOB)))
    detached_utxos.get(*outpoint).amount = 555
    detached_utxos.spend(*outpoint)
    detached_utxos.add("foreign", 0, TxOutput(444, ALICE))
    entries = chain.get_utxos_for_address(BOB)
    entries[outpoint].amount = 333
    entries.clear()

    assert snapshot(chain) == expected
    assert chain.validate_chain(current_time=NOW)


def test_independent_chains_do_not_share_utxos_or_transaction_history():
    first, funding = funded_chain()
    second = Blockchain()

    assert first.get_balance(ALICE) == 50
    assert first.has_transaction(funding.txid())
    assert second.get_balance(ALICE) == 0
    assert not second.has_transaction(funding.txid())
    assert second.get_utxos_for_address(ALICE) == {}


@pytest.mark.parametrize("corruption", ["utxo", "history"])
def test_chain_audit_detects_cached_state_that_disagrees_with_replay(corruption):
    chain, funding = funded_chain()
    if corruption == "utxo":
        chain._state.utxo_set.spend(funding.txid(), 0)
    else:
        chain._state.seen_txids.clear()

    # Deliberately corrupt private state to simulate a cache bug. Historical
    # blocks remain valid, but the owning chain must detect the disagreement.
    assert validate_chain(chain.chain, current_time=NOW)
    assert not chain.validate_chain(current_time=NOW)


def test_automatic_template_timestamps_avoid_repeated_coinbase_txids(monkeypatch):
    monkeypatch.setattr("mining.block_template.time.time", lambda: GENESIS_TIMESTAMP)
    chain = Blockchain()
    ids = set()
    for height in range(1, 4):
        template = chain.create_block_template(ALICE)
        assert template.timestamp == GENESIS_TIMESTAMP + height
        assert template.transactions[0].txid() not in ids
        ids.add(template.transactions[0].txid())
        assert chain.add_block(mine(template), current_time=NOW)
    assert chain.get_balance(ALICE) == 150

    with pytest.raises(ValueError, match="Coinbase TXID"):
        chain.create_block_template(ALICE, timestamp=chain.get_latest_block().timestamp)
