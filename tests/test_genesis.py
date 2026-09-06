from blockchain.block import Block
from blockchain.genesis import (
    GENESIS_HASH,
    GENESIS_TIMESTAMP,
    create_genesis_block,
    is_genesis_block,
)
from transaction.transaction import Transaction


def test_genesis_matches_fixed_network_values():
    block = create_genesis_block()

    assert block.previous_block_hash == "0" * 64
    assert block.timestamp == GENESIS_TIMESTAMP
    assert block.transactions == []
    assert block.merkle_root == (
        "e3b0c44298fc1c149afbf4c8996fb924"
        "27ae41e4649b934ca495991b7852b855"
    )
    assert block.hash() == GENESIS_HASH
    assert block.hash() == (
        "14c5baf99007aba3bca5d4a32a5dd213"
        "4495a6bdaef5586f515d0f838b654e6a"
    )
    assert is_genesis_block(block)


def test_genesis_calls_return_independent_objects():
    first = create_genesis_block()
    second = create_genesis_block()

    assert first is not second
    assert first.transactions is not second.transactions
    first.nonce += 1
    assert second.hash() == GENESIS_HASH


def test_zero_previous_hash_does_not_make_a_genesis():
    fake = Block(
        transactions=[],
        previous_block_hash="0" * 64,
        timestamp=GENESIS_TIMESTAMP + 1,
    )

    assert not is_genesis_block(fake)


def test_genesis_body_must_stay_empty_even_if_header_is_unchanged():
    block = create_genesis_block()
    block.transactions.append(
        Transaction(inputs=[], outputs=[], timestamp=GENESIS_TIMESTAMP)
    )

    assert block.hash() == GENESIS_HASH
    assert not is_genesis_block(block)
