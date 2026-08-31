from crypto.keys import (
    generate_private_key,
    public_key_from_hex,
)
from crypto.signature import verify_signature

from transaction.transaction import Transaction
from transaction.tx_input import TxInput
from transaction.tx_output import TxOutput


def create_transaction():
    return Transaction(
        inputs=[
            TxInput(
                previous_tx_id="funding",
                output_index=0,
            )
        ],
        outputs=[
            TxOutput(
                amount=6,
                recipient_address="PYC_BOB",
            ),
            TxOutput(
                amount=3,
                recipient_address="PYC_ALICE",
            ),
        ],
        timestamp=1234567890,
    )


def test_sign_input():
    private_key = generate_private_key()

    transaction = create_transaction()

    transaction.sign_input(
        0,
        private_key,
    )

    assert transaction.inputs[0].public_key
    assert transaction.inputs[0].signature


def test_signature_is_valid():
    private_key = generate_private_key()

    transaction = create_transaction()

    transaction.sign_input(
        0,
        private_key,
    )

    public_key = public_key_from_hex(
        transaction.inputs[0].public_key
    )

    signature = bytes.fromhex(
        transaction.inputs[0].signature
    )

    assert verify_signature(
        public_key,
        transaction.signing_bytes(0),
        signature,
    )


def test_txid_is_deterministic():
    private_key = generate_private_key()

    transaction = create_transaction()

    transaction.sign_input(
        0,
        private_key,
    )

    txid1 = transaction.txid()
    txid2 = transaction.txid()

    assert txid1 == txid2


def test_modify_transaction_changes_txid():
    private_key = generate_private_key()

    transaction = create_transaction()

    transaction.sign_input(
        0,
        private_key,
    )

    original_txid = transaction.txid()

    transaction.outputs[0].amount = 7

    assert transaction.txid() != original_txid
