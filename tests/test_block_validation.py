from copy import deepcopy

import pytest

from blockchain.block import Block
from blockchain.chainstate import ChainState
from blockchain.genesis import GENESIS_TIMESTAMP, create_genesis_block
from blockchain.merkle import calculate_merkle_root
from blockchain.validation import (
    MAX_FUTURE_BLOCK_TIME,
    validate_block,
    validate_block_header,
    validate_block_structure,
    validate_chain,
    validate_non_genesis_block_body,
)
from consensus.pow import validate_proof_of_work
from crypto.address import public_key_to_address
from crypto.keys import generate_private_key, get_public_key
from mining.block_template import create_block_template
from mining.coinbase import create_coinbase_transaction
from mining.miner import mine_block
from transaction.transaction import Transaction
from transaction.tx_input import TxInput
from transaction.tx_output import TxOutput
from transaction.utxo import UTXOSet
from transaction.validation import validate_transaction


NOW = GENESIS_TIMESTAMP + 100


def make_address() -> str:
    private_key = generate_private_key()
    return public_key_to_address(get_public_key(private_key))


def make_payload(amount: int) -> Transaction:
    # Payload chỉ phục vụ kiểm tra Merkle/body. Tính hợp lệ trên UTXO là Phase 6.
    return Transaction(
        inputs=[TxInput(previous_tx_id="funding", output_index=0)],
        outputs=[TxOutput(amount=amount, recipient_address=make_address())],
        timestamp=GENESIS_TIMESTAMP,
    )


def make_child(
    parent: Block,
    transactions: list[Transaction] | None = None,
    *,
    timestamp: int | None = None,
) -> Block:
    template = create_block_template(
        parent,
        make_address(),
        timestamp=(parent.timestamp + 1 if timestamp is None else timestamp),
    )
    # Raw payloads here intentionally exercise structure, not ledger validity.
    template.transactions.extend([] if transactions is None else transactions)
    template.refresh_merkle_root()
    mined = mine_block(template, max_nonce=100_000)
    assert mined is not None
    return mined


def remine(block: Block) -> Block:
    mined = mine_block(block, max_nonce=100_000)
    assert mined is not None
    return mined


def make_proof_invalid(block: Block) -> None:
    block.nonce += 1

    while validate_proof_of_work(block):
        block.nonce += 1


def test_valid_mined_block_and_chain():
    genesis = create_genesis_block()
    child = make_child(genesis)

    assert validate_block_structure(child)
    assert validate_non_genesis_block_body(child)
    assert validate_proof_of_work(child)
    assert validate_block_header(child, genesis, current_time=NOW)
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
    block = make_child(create_genesis_block())
    block.transactions[0].outputs = [object()]

    assert not validate_block_structure(block)


def test_wrong_parent_hash_is_rejected():
    genesis = create_genesis_block()
    child = make_child(genesis)
    child.previous_block_hash = "f" * 64

    assert validate_block_structure(child)
    assert not validate_block_header(child, genesis, current_time=NOW)


def test_timestamp_can_equal_parent_but_cannot_go_backwards():
    genesis = create_genesis_block()
    child = make_child(genesis, timestamp=genesis.timestamp)

    assert validate_block_header(child, genesis, current_time=NOW)

    child.timestamp -= 1
    assert not validate_block_header(child, genesis, current_time=NOW)


def test_future_timestamp_boundary():
    genesis = create_genesis_block()
    child = make_child(
        genesis,
        timestamp=NOW + MAX_FUTURE_BLOCK_TIME,
    )
    assert validate_block_header(child, genesis, current_time=NOW)

    too_far = make_child(
        genesis,
        timestamp=NOW + MAX_FUTURE_BLOCK_TIME + 1,
    )
    assert not validate_block_header(too_far, genesis, current_time=NOW)


def test_merkle_validation_detects_changed_body_without_repairing_it():
    child = make_child(create_genesis_block(), [make_payload(1)])
    claimed_root = child.merkle_root
    old_hash = child.hash()
    child.transactions[1].outputs[0].amount = 999

    assert child.hash() == old_hash
    assert not validate_block_structure(child)
    assert child.merkle_root == claimed_root


def test_wrong_claimed_merkle_root_is_rejected():
    child = make_child(create_genesis_block())
    child.merkle_root = "f" * 64

    assert not validate_block_structure(child)


def test_reordering_regular_transactions_without_refresh_is_rejected():
    child = make_child(
        create_genesis_block(),
        [make_payload(1), make_payload(2)],
    )
    child.transactions[1:] = reversed(child.transactions[1:])

    assert not validate_block_structure(child)


def test_duplicate_last_tx_is_rejected_even_when_merkle_root_matches():
    child = make_child(
        create_genesis_block(),
        [make_payload(1), make_payload(2)],
    )
    child.transactions.append(deepcopy(child.transactions[-1]))

    # Ba leaves ban đầu được padding bằng leaf cuối, nên body bốn leaves này
    # có cùng root nếu chỉ nhìn Merkle tree.
    assert calculate_merkle_root(child.transactions) == child.merkle_root
    assert not validate_block_structure(child)


@pytest.mark.parametrize("blocks", [[], None])
def test_chain_requires_genesis(blocks):
    assert not validate_chain(blocks, current_time=NOW)


def test_altered_genesis_cannot_anchor_a_chain():
    fake = create_genesis_block()
    fake.nonce += 1
    child = make_child(fake)

    # Pairwise validation trusts the supplied parent; full-chain validation
    # additionally anchors at this network's fixed genesis.
    assert validate_block_header(child, fake, current_time=NOW)
    assert not validate_chain([fake, child], current_time=NOW)


def test_tampering_middle_header_breaks_next_link_and_pow():
    genesis = create_genesis_block()
    first = make_child(genesis)
    second = make_child(first)
    make_proof_invalid(first)

    assert not validate_chain([genesis, first, second], current_time=NOW)


def test_relinking_a_descendant_requires_mining_it_again():
    genesis = create_genesis_block()
    first = make_child(genesis)
    second = make_child(first)
    old_first_hash = first.hash()

    # Tìm một header hợp lệ mới cho first sao cho second, sau khi cập nhật link,
    # được biết chắc là không đạt target. Không giả định nonce + 1 luôn fail.
    first.nonce += 1
    while True:
        if validate_proof_of_work(first):
            second.previous_block_hash = first.hash()

            if not validate_proof_of_work(second):
                break

        first.nonce += 1

    assert first.hash() != old_first_hash
    assert validate_block_header(first, genesis, current_time=NOW)
    assert not validate_block_header(second, first, current_time=NOW)
    assert not validate_chain([genesis, first, second], current_time=NOW)

    reminted_second = remine(second)
    assert validate_chain(
        [genesis, first, reminted_second],
        current_time=NOW,
    )


def test_block_body_requires_first_and_only_coinbase():
    genesis = create_genesis_block()
    child = make_child(genesis, [make_payload(1)])

    child.transactions[0], child.transactions[1] = (
        child.transactions[1],
        child.transactions[0],
    )
    child.refresh_merkle_root()
    child = remine(child)

    assert validate_block_structure(child)
    assert not validate_non_genesis_block_body(child)
    assert not validate_block_header(child, genesis, current_time=NOW)


def test_non_genesis_empty_block_is_rejected_even_if_it_is_mined():
    genesis = create_genesis_block()
    child = make_child(genesis)
    child.transactions.clear()
    child.refresh_merkle_root()
    child = remine(child)

    assert validate_block_structure(child)
    assert not validate_non_genesis_block_body(child)
    assert not validate_block_header(child, genesis, current_time=NOW)


def test_block_body_rejects_a_second_zero_input_transaction():
    genesis = create_genesis_block()
    child = make_child(genesis)
    child.transactions.append(
        create_coinbase_transaction(
            make_address(),
            timestamp=child.timestamp,
        )
    )
    child.refresh_merkle_root()
    child = remine(child)

    assert validate_block_structure(child)
    assert not validate_non_genesis_block_body(child)
    assert not validate_block_header(child, genesis, current_time=NOW)


def test_expected_difficulty_and_pow_are_required_before_acceptance():
    genesis = create_genesis_block()
    child = make_child(genesis)
    child.difficulty = 1
    child = remine(child)

    assert validate_proof_of_work(child)
    assert not validate_block_header(child, genesis, current_time=NOW)

    child = make_child(genesis)
    make_proof_invalid(child)

    assert not validate_block_header(child, genesis, current_time=NOW)


def test_stateless_checks_do_not_replace_full_ledger_validation():
    payload = make_payload(1)
    genesis = create_genesis_block()
    child = make_child(genesis, [payload])

    assert validate_block_structure(child)
    assert validate_non_genesis_block_body(child)
    assert validate_block_header(child, genesis, current_time=NOW)
    assert not validate_transaction(payload, UTXOSet())
    assert not validate_block(child, genesis, state=ChainState(), current_time=NOW)
    assert not validate_chain([genesis, child], current_time=NOW)
