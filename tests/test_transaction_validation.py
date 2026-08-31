from crypto.address import public_key_to_address
from crypto.keys import (
    generate_private_key,
    get_public_key,
)

from transaction.transaction import Transaction
from transaction.tx_input import TxInput
from transaction.tx_output import TxOutput
from transaction.utxo import UTXOSet

from transaction.validation import (
    calculate_transaction_fee,
    validate_transaction,
)


def create_valid_transaction():

    alice_private = generate_private_key()
    bob_private = generate_private_key()

    alice_public = get_public_key(
        alice_private
    )

    bob_public = get_public_key(
        bob_private
    )

    alice_address = (
        public_key_to_address(
            alice_public
        )
    )

    bob_address = (
        public_key_to_address(
            bob_public
        )
    )

    utxos = UTXOSet()

    # Alice hiện sở hữu 10 PYC.
    utxos.add(
        "funding",
        0,
        TxOutput(
            amount=10,
            recipient_address=alice_address,
        ),
    )

    transaction = Transaction(
        inputs=[
            TxInput(
                previous_tx_id="funding",
                output_index=0,
            )
        ],
        outputs=[
            TxOutput(
                amount=6,
                recipient_address=bob_address,
            ),
            TxOutput(
                amount=3,
                recipient_address=alice_address,
            ),
        ],
        timestamp=1234567890,
    )

    transaction.sign_input(
        0,
        alice_private,
    )

    return (
        transaction,
        utxos,
        alice_private,
        bob_private,
    )


def test_valid_transaction():
    transaction, utxos, _, _ = (
        create_valid_transaction()
    )

    assert validate_transaction(
        transaction,
        utxos,
    )


def test_transaction_fee():
    transaction, utxos, _, _ = (
        create_valid_transaction()
    )

    assert calculate_transaction_fee(
        transaction,
        utxos,
    ) == 1


def test_wrong_owner():
    (
        transaction,
        utxos,
        _,
        bob_private,
    ) = create_valid_transaction()

    # Bob thử ký UTXO của Alice.
    transaction.sign_input(
        0,
        bob_private,
    )

    assert not validate_transaction(
        transaction,
        utxos,
    )


def test_modified_amount():
    transaction, utxos, _, _ = (
        create_valid_transaction()
    )

    # Transaction đã ký xong nhưng
    # attacker sửa amount.
    transaction.outputs[0].amount = 7

    assert not validate_transaction(
        transaction,
        utxos,
    )


def test_missing_utxo():
    transaction, _, _, _ = (
        create_valid_transaction()
    )

    empty_utxos = UTXOSet()

    assert not validate_transaction(
        transaction,
        empty_utxos,
    )


def test_output_exceeds_input():
    (
        transaction,
        utxos,
        alice_private,
        _,
    ) = create_valid_transaction()

    transaction.outputs[0].amount = 20

    # Phải ký lại để tránh fail chỉ
    # vì signature cũ.
    transaction.sign_input(
        0,
        alice_private,
    )

    assert not validate_transaction(
        transaction,
        utxos,
    )


def test_double_spend():
    transaction, utxos, _, _ = (
        create_valid_transaction()
    )

    assert validate_transaction(
        transaction,
        utxos,
    )

    # Transaction thứ nhất đã tiêu UTXO.
    utxos.apply_valid_transaction(
        transaction
    )

    # Transaction cũ cố dùng lại
    # funding:0.
    assert not validate_transaction(
        transaction,
        utxos,
    )
