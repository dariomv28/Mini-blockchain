from copy import deepcopy

import pytest

from blockchain.block import Block
from blockchain.genesis import GENESIS_TIMESTAMP, create_genesis_block
from blockchain.merkle import calculate_merkle_root
from blockchain.validation import (
    MAX_FUTURE_BLOCK_TIME,
    validate_block,
    validate_block_structure,
    validate_chain,
)
from transaction.transaction import Transaction
from transaction.tx_output import TxOutput
from transaction.utxo import UTXOSet
from transaction.validation import validate_transaction


NOW = GENESIS_TIMESTAMP + 100


def make_payload(amount: int) -> Transaction:
    # Payload chỉ phục vụ test Merkle, không phải giao dịch chuyển coin.
    return Transaction(
        inputs=[],
        outputs=[TxOutput(amount=amount, recipient_address="PYC_TEST")],
        timestamp=GENESIS_TIMESTAMP,
    )


def make_child(parent: Block, transactions=None) -> Block:
    return Block(
        transactions=[] if transactions is None else transactions,
        previous_block_hash=parent.hash(),
        timestamp=parent.timestamp + 1,
    )


def test_valid_empty_block_and_chain():
    genesis = create_genesis_block()
    child = make_child(genesis)

    assert validate_block_structure(child)
    assert validate_block(child, genesis, current_time=NOW)
    assert validate_chain([genesis, child], current_time=NOW)


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("version", True),
        ("version", 2),
        ("timestamp", -1),
        ("timestamp", 1.5),
        ("timestamp", True),
        ("difficulty", 0),
        ("difficulty", True),
        ("nonce", -1),
        ("nonce", True),
        ("previous_block_hash", "abc"),
        ("previous_block_hash", "g" * 64),
        ("previous_block_hash", "A" * 64),
        ("merkle_root", "z" * 64),
    ],
)
def test_invalid_header_fields_are_rejected(field, value):
    block = make_child(create_genesis_block())
    setattr(block, field, value)

    assert not validate_block_structure(block)


@pytest.mark.parametrize("transactions", [None, (), ["not a transaction"]])
def test_invalid_transaction_container_is_rejected(transactions):
    block = make_child(create_genesis_block())
    block.transactions = transactions

    assert not validate_block_structure(block)


def test_broken_transaction_serialization_returns_false():
    block = make_child(create_genesis_block(), [make_payload(1)])
    block.transactions[0].outputs = [object()]

    assert not validate_block_structure(block)


def test_wrong_parent_hash_is_rejected():
    genesis = create_genesis_block()
    child = make_child(genesis)
    child.previous_block_hash = "f" * 64

    assert validate_block_structure(child)
    assert not validate_block(child, genesis, current_time=NOW)


def test_timestamp_can_equal_parent_but_cannot_go_backwards():
    genesis = create_genesis_block()
    child = make_child(genesis)
    child.timestamp = genesis.timestamp
    assert validate_block(child, genesis, current_time=NOW)

    child.timestamp -= 1
    assert not validate_block(child, genesis, current_time=NOW)


def test_future_timestamp_boundary():
    genesis = create_genesis_block()
    child = make_child(genesis)
    child.timestamp = NOW + MAX_FUTURE_BLOCK_TIME
    assert validate_block(child, genesis, current_time=NOW)

    child.timestamp += 1
    assert not validate_block(child, genesis, current_time=NOW)


def test_merkle_validation_detects_changed_body_without_repairing_it():
    child = make_child(create_genesis_block(), [make_payload(1)])
    claimed_root = child.merkle_root
    old_hash = child.hash()
    child.transactions[0].outputs[0].amount = 999

    assert child.hash() == old_hash
    assert not validate_block_structure(child)
    assert child.merkle_root == claimed_root


def test_wrong_claimed_merkle_root_is_rejected():
    child = make_child(create_genesis_block())
    child.merkle_root = "f" * 64

    assert not validate_block_structure(child)


def test_reordering_transactions_without_refresh_is_rejected():
    child = make_child(
        create_genesis_block(),
        [make_payload(1), make_payload(2)],
    )
    child.transactions.reverse()

    assert not validate_block_structure(child)


def test_duplicate_last_tx_is_rejected_even_when_merkle_root_matches():
    child = make_child(
        create_genesis_block(),
        [make_payload(1), make_payload(2), make_payload(3)],
    )
    child.transactions.append(deepcopy(child.transactions[-1]))

    # Quy tắc nhân đôi leaf lẻ làm hai body này có cùng root.
    assert calculate_merkle_root(child.transactions) == child.merkle_root
    assert not validate_block_structure(child)


@pytest.mark.parametrize("blocks", [[], None])
def test_chain_requires_genesis(blocks):
    assert not validate_chain(blocks, current_time=NOW)


def test_altered_genesis_cannot_anchor_a_chain():
    fake = create_genesis_block()
    fake.nonce += 1
    child = make_child(fake)

    assert validate_block(child, fake, current_time=NOW)
    assert not validate_chain([fake, child], current_time=NOW)


def test_tampering_middle_header_breaks_next_link():
    genesis = create_genesis_block()
    first = make_child(genesis)
    second = make_child(first)
    first.nonce += 1

    assert not validate_chain([genesis, first, second], current_time=NOW)


def test_structural_validation_does_not_confirm_coin_transfer():
    payload = make_payload(1)
    child = make_child(create_genesis_block(), [payload])

    assert validate_block_structure(child)
    assert not validate_transaction(payload, UTXOSet())


def test_rewriting_links_is_possible_without_consensus_rules():
    genesis = create_genesis_block()
    first = make_child(genesis)
    second = make_child(first)
    first.nonce += 1
    second.previous_block_hash = first.hash()

    # Phase 4 chỉ phát hiện sự không khớp; chưa có PoW/fork choice.
    assert validate_chain([genesis, first, second], current_time=NOW)
