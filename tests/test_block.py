from blockchain.block import Block
from blockchain.merkle import (
    calculate_merkle_root,
)
from transaction.transaction import Transaction
from transaction.tx_output import TxOutput


def make_transaction(
    amount: int,
    timestamp: int,
) -> Transaction:
    return Transaction(
        inputs=[],
        outputs=[
            TxOutput(
                amount=amount,
                recipient_address="PYC_TEST",
            )
        ],
        timestamp=timestamp,
    )


def test_block_calculates_merkle_root():
    tx1 = make_transaction(1, 1)
    tx2 = make_transaction(2, 2)

    block = Block(
        transactions=[tx1, tx2],
        previous_block_hash="0" * 64,
        timestamp=100,
    )

    assert (
        block.merkle_root
        == calculate_merkle_root(
            [tx1, tx2]
        )
    )


def test_block_hash_equals_header_hash():
    tx = make_transaction(1, 1)

    block = Block(
        transactions=[tx],
        previous_block_hash="0" * 64,
        timestamp=100,
    )

    assert (
        block.hash()
        == block.header().hash()
    )


def test_same_block_data_same_hash():
    tx1 = make_transaction(1, 1)
    tx2 = make_transaction(1, 1)

    block_a = Block(
        transactions=[tx1],
        previous_block_hash="0" * 64,
        timestamp=100,
        version=1,
        difficulty=1,
        nonce=0,
    )

    block_b = Block(
        transactions=[tx2],
        previous_block_hash="0" * 64,
        timestamp=100,
        version=1,
        difficulty=1,
        nonce=0,
    )

    assert block_a.hash() == block_b.hash()


def test_changing_nonce_changes_block_hash():
    tx = make_transaction(1, 1)

    block = Block(
        transactions=[tx],
        previous_block_hash="0" * 64,
        timestamp=100,
    )

    old_hash = block.hash()

    block.nonce += 1

    new_hash = block.hash()

    assert old_hash != new_hash


def test_refresh_merkle_root_after_append():
    tx1 = make_transaction(1, 1)
    tx2 = make_transaction(2, 2)

    block = Block(
        transactions=[tx1],
        previous_block_hash="0" * 64,
        timestamp=100,
    )

    old_root = block.merkle_root

    block.transactions.append(tx2)
    block.refresh_merkle_root()

    assert block.merkle_root != old_root

    assert (
        block.merkle_root
        == calculate_merkle_root(
            [tx1, tx2]
        )
    )


def test_block_to_dict():
    tx = make_transaction(1, 1)

    block = Block(
        transactions=[tx],
        previous_block_hash="0" * 64,
        timestamp=100,
    )

    data = block.to_dict()

    assert "header" in data
    assert "transactions" in data

    assert (
        data["header"]["merkle_root"]
        == block.merkle_root
    )

    assert len(data["transactions"]) == 1
