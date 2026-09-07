from crypto.address import public_key_to_address
from crypto.keys import generate_private_key, get_public_key
from mining.coinbase import (
    BLOCK_SUBSIDY,
    create_coinbase_transaction,
    is_coinbase_transaction,
    validate_coinbase_transaction,
)
from transaction.tx_input import TxInput
from transaction.utxo import UTXOSet
from transaction.validation import validate_transaction


TIMESTAMP = 123_456


def make_address() -> str:
    private_key = generate_private_key()
    return public_key_to_address(get_public_key(private_key))


def test_create_and_validate_a_fixed_subsidy_coinbase():
    transaction = create_coinbase_transaction(
        make_address(),
        timestamp=TIMESTAMP,
    )

    assert is_coinbase_transaction(transaction)
    assert transaction.outputs[0].amount == BLOCK_SUBSIDY
    assert validate_coinbase_transaction(
        transaction,
        block_timestamp=TIMESTAMP,
    )

    # A normal transfer validator must retain its Phase 2 rule.
    assert not validate_transaction(transaction, UTXOSet())


def test_coinbase_rejects_wrong_reward_or_destination():
    transaction = create_coinbase_transaction(
        make_address(),
        timestamp=TIMESTAMP,
    )
    transaction.outputs[0].amount = BLOCK_SUBSIDY + 1

    assert not validate_coinbase_transaction(
        transaction,
        block_timestamp=TIMESTAMP,
    )

    transaction.outputs[0].amount = BLOCK_SUBSIDY
    transaction.outputs[0].recipient_address = "PYC_NOT_A_VALID_ADDRESS"

    assert not validate_coinbase_transaction(
        transaction,
        block_timestamp=TIMESTAMP,
    )


def test_coinbase_rejects_inputs_extra_outputs_and_wrong_timestamp():
    transaction = create_coinbase_transaction(
        make_address(),
        timestamp=TIMESTAMP,
    )
    transaction.inputs.append(TxInput("funding", 0))

    assert not is_coinbase_transaction(transaction)
    assert not validate_coinbase_transaction(
        transaction,
        block_timestamp=TIMESTAMP,
    )

    transaction = create_coinbase_transaction(
        make_address(),
        timestamp=TIMESTAMP,
    )
    transaction.outputs.append(transaction.outputs[0])

    assert not validate_coinbase_transaction(
        transaction,
        block_timestamp=TIMESTAMP,
    )

    transaction = create_coinbase_transaction(
        make_address(),
        timestamp=TIMESTAMP,
    )

    assert not validate_coinbase_transaction(
        transaction,
        block_timestamp=TIMESTAMP + 1,
    )

    transaction = create_coinbase_transaction(
        make_address(),
        timestamp=1,
    )
    transaction.timestamp = True

    # Python considers True == 1, but consensus fields must be real integers.
    assert not validate_coinbase_transaction(
        transaction,
        block_timestamp=1,
    )
