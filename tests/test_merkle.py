from blockchain.merkle import (
    calculate_merkle_root,
    calculate_merkle_root_from_txids,
)
from crypto.hash import sha256_hex
from transaction.transaction import Transaction
from transaction.tx_output import TxOutput


def test_empty_merkle_root():
    assert (
        calculate_merkle_root_from_txids([])
        == sha256_hex(b"")
    )


def test_single_txid_is_merkle_root():
    txid = sha256_hex(b"tx-1")

    assert (
        calculate_merkle_root_from_txids(
            [txid]
        )
        == txid
    )


def test_two_txids_merkle_root():
    txid_a = sha256_hex(b"tx-a")
    txid_b = sha256_hex(b"tx-b")

    expected = sha256_hex(
        bytes.fromhex(txid_a)
        + bytes.fromhex(txid_b)
    )

    assert (
        calculate_merkle_root_from_txids(
            [txid_a, txid_b]
        )
        == expected
    )


def test_odd_number_duplicates_last_hash():
    txid_a = sha256_hex(b"tx-a")
    txid_b = sha256_hex(b"tx-b")
    txid_c = sha256_hex(b"tx-c")

    left_parent = sha256_hex(
        bytes.fromhex(txid_a)
        + bytes.fromhex(txid_b)
    )

    right_parent = sha256_hex(
        bytes.fromhex(txid_c)
        + bytes.fromhex(txid_c)
    )

    expected = sha256_hex(
        bytes.fromhex(left_parent)
        + bytes.fromhex(right_parent)
    )

    assert (
        calculate_merkle_root_from_txids(
            [
                txid_a,
                txid_b,
                txid_c,
            ]
        )
        == expected
    )


def test_merkle_root_depends_on_order():
    txid_a = sha256_hex(b"tx-a")
    txid_b = sha256_hex(b"tx-b")

    root_ab = (
        calculate_merkle_root_from_txids(
            [txid_a, txid_b]
        )
    )

    root_ba = (
        calculate_merkle_root_from_txids(
            [txid_b, txid_a]
        )
    )

    assert root_ab != root_ba


def test_merkle_root_from_transactions():
    tx1 = Transaction(
        inputs=[],
        outputs=[
            TxOutput(
                amount=1,
                recipient_address="A",
            )
        ],
        timestamp=1,
    )

    tx2 = Transaction(
        inputs=[],
        outputs=[
            TxOutput(
                amount=2,
                recipient_address="B",
            )
        ],
        timestamp=2,
    )

    expected = (
        calculate_merkle_root_from_txids(
            [
                tx1.txid(),
                tx2.txid(),
            ]
        )
    )

    assert (
        calculate_merkle_root(
            [tx1, tx2]
        )
        == expected
    )
