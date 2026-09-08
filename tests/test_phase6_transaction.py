from copy import deepcopy

import pytest
from ecdsa import SECP256k1, SigningKey

from crypto.address import public_key_to_address
from transaction.transaction import Transaction
from transaction.tx_input import TxInput
from transaction.tx_output import TxOutput
from transaction.utxo import UTXOSet
from transaction.validation import calculate_transaction_fee, validate_transaction


@pytest.fixture
def funded_transaction():
    owner = SigningKey.from_secret_exponent(1, curve=SECP256k1)
    address = public_key_to_address(owner.get_verifying_key())
    utxos = UTXOSet()
    utxos.add("funding", 0, TxOutput(10, address))
    transaction = Transaction(
        inputs=[TxInput("funding", 0)],
        outputs=[TxOutput(9, address)],
        timestamp=123,
    )
    transaction.sign_input(0, owner)
    return transaction, utxos, owner


def assert_invalid(transaction, utxos):
    assert not validate_transaction(transaction, utxos)
    with pytest.raises(ValueError, match="invalid transaction"):
        calculate_transaction_fee(transaction, utxos)


@pytest.mark.parametrize("malformed", [None, {}, [], "transaction", 1, True])
def test_non_transaction_values_fail_closed(funded_transaction, malformed):
    _, utxos, _ = funded_transaction
    assert_invalid(malformed, utxos)


@pytest.mark.parametrize(
    "field,value",
    [
        ("version", True),
        ("version", 1.0),
        ("version", "1"),
        ("version", 2),
        ("timestamp", False),
        ("timestamp", -1),
        ("timestamp", 123.0),
        ("timestamp", "123"),
        ("inputs", None),
        ("inputs", {}),
        ("inputs", (TxInput("funding", 0),)),
        ("inputs", [None]),
        ("inputs", [{}]),
        ("inputs", []),
        ("outputs", None),
        ("outputs", {}),
        ("outputs", (TxOutput(1, "Alice"),)),
        ("outputs", [None]),
        ("outputs", [{}]),
        ("outputs", []),
    ],
)
def test_malformed_transaction_fields_fail_closed(funded_transaction, field, value):
    transaction, utxos, _ = funded_transaction
    setattr(transaction, field, value)
    assert_invalid(transaction, utxos)


@pytest.mark.parametrize(
    "field,value",
    [
        ("previous_tx_id", None),
        ("previous_tx_id", []),
        ("previous_tx_id", 1),
        ("previous_tx_id", ""),
        ("output_index", False),
        ("output_index", -1),
        ("output_index", 0.0),
        ("output_index", "0"),
        ("public_key", None),
        ("public_key", []),
        ("public_key", ""),
        ("public_key", "zz"),
        ("public_key", "00" * 64),
        ("signature", None),
        ("signature", []),
        ("signature", ""),
        ("signature", "zz"),
        ("signature", "00"),
        ("signature", "00" * 64),
    ],
)
def test_malformed_input_fields_fail_closed(funded_transaction, field, value):
    transaction, utxos, _ = funded_transaction
    setattr(transaction.inputs[0], field, value)
    assert_invalid(transaction, utxos)


@pytest.mark.parametrize("amount", [True, False, 0, -1, 1.5, "9", None])
def test_invalid_output_amounts_fail_closed(funded_transaction, amount):
    transaction, utxos, _ = funded_transaction
    transaction.outputs[0].amount = amount
    assert_invalid(transaction, utxos)


@pytest.mark.parametrize("address", [None, [], {}, True, "", "Alice", "PYC_123"])
def test_invalid_output_addresses_fail_closed(funded_transaction, address):
    transaction, utxos, _ = funded_transaction
    transaction.outputs[0].recipient_address = address
    assert_invalid(transaction, utxos)


def test_bool_outpoint_is_rejected_even_with_a_valid_signature(funded_transaction):
    transaction, utxos, owner = funded_transaction
    transaction.inputs[0].output_index = False
    transaction.sign_input(0, owner)
    assert_invalid(transaction, utxos)


def test_duplicate_inputs_cannot_inflate_available_value(funded_transaction):
    transaction, utxos, owner = funded_transaction
    transaction.inputs.append(deepcopy(transaction.inputs[0]))
    transaction.outputs[0].amount = 19
    for index in range(2):
        transaction.sign_input(index, owner)
    assert_invalid(transaction, utxos)


@pytest.mark.parametrize("amount", [True, 0, -10, "10", None])
def test_corrupt_utxo_amounts_fail_closed(funded_transaction, amount):
    transaction, utxos, _ = funded_transaction
    address = transaction.outputs[0].recipient_address
    utxos.spend("funding", 0)
    utxos.add("funding", 0, TxOutput(amount, address))
    assert_invalid(transaction, utxos)


def test_corrupt_utxo_shape_fails_closed(funded_transaction):
    transaction, utxos, _ = funded_transaction
    utxos._utxos[("funding", 0)] = {"amount": 10}
    assert_invalid(transaction, utxos)


def test_wrong_owner_and_overspend_cannot_produce_fees(funded_transaction):
    transaction, utxos, owner = funded_transaction
    stranger = SigningKey.from_secret_exponent(2, curve=SECP256k1)
    transaction.sign_input(0, stranger)
    assert_invalid(transaction, utxos)
    transaction.outputs[0].amount = 11
    transaction.sign_input(0, owner)
    assert_invalid(transaction, utxos)


def test_zero_fee_and_timestamp_zero_are_valid(funded_transaction):
    transaction, utxos, owner = funded_transaction
    transaction.timestamp = 0
    transaction.outputs[0].amount = 10
    transaction.sign_input(0, owner)
    assert validate_transaction(transaction, utxos)
    assert calculate_transaction_fee(transaction, utxos) == 0


def test_validation_and_fee_queries_do_not_change_state(funded_transaction):
    transaction, utxos, _ = funded_transaction
    before_tx = deepcopy(transaction)
    before_utxos = utxos.to_dict()
    assert validate_transaction(transaction, utxos)
    assert calculate_transaction_fee(transaction, utxos) == 1
    assert transaction == before_tx
    assert utxos.to_dict() == before_utxos


def test_utxo_views_and_copies_are_independent():
    output = TxOutput(10, "Alice")
    utxos = UTXOSet()
    utxos.add("funding", 0, output)
    utxos.add("other", 1, TxOutput(3, "Bob"))
    output.amount = 999
    fetched = utxos.get("funding", 0)
    fetched.amount = 888
    snapshot = utxos.to_dict()
    snapshot[("funding", 0)].amount = 777
    snapshot.clear()
    address_view = utxos.get_utxos_for_address("Alice")
    assert set(address_view) == {("funding", 0)}
    address_view[("funding", 0)].amount = 666
    clone = utxos.copy()
    clone.spend("funding", 0)
    clone.add("new", 0, TxOutput(5, "Alice"))
    assert utxos.get("funding", 0) == TxOutput(10, "Alice")
    assert utxos.get_balance("Alice") == 10
    assert len(utxos) == 2
    assert not utxos.exists("new", 0)
    assert utxos.get_utxos_for_address("unknown") == {}


def test_spent_output_does_not_alias_another_stored_output():
    utxos = UTXOSet()
    output = TxOutput(10, "Alice")
    utxos.add("funding", 0, output)
    utxos.add("funding", 1, output)
    spent = utxos.spend("funding", 0)
    spent.amount = 100
    assert utxos.get("funding", 1).amount == 10


def test_add_refuses_to_overwrite_existing_outpoint():
    utxos = UTXOSet()
    utxos.add("funding", 0, TxOutput(10, "Alice"))
    with pytest.raises(ValueError, match="already exists"):
        utxos.add("funding", 0, TxOutput(100, "Bob"))
    assert utxos.to_dict() == {("funding", 0): TxOutput(10, "Alice")}


@pytest.mark.parametrize("failure", ["missing_input", "duplicate_input", "collision"])
def test_apply_is_atomic_on_invalid_outpoints(funded_transaction, failure):
    transaction, utxos, _ = funded_transaction
    if failure == "missing_input":
        transaction.inputs.append(TxInput("missing", 0))
        error = KeyError
    elif failure == "duplicate_input":
        transaction.inputs.append(deepcopy(transaction.inputs[0]))
        error = ValueError
    else:
        utxos.add(transaction.txid(), 0, TxOutput(100, "other"))
        error = ValueError
    before = utxos.to_dict()
    with pytest.raises(error):
        utxos.apply_valid_transaction(transaction)
    assert utxos.to_dict() == before


def test_add_outputs_collision_is_atomic(funded_transaction):
    transaction, utxos, _ = funded_transaction
    transaction.outputs.append(deepcopy(transaction.outputs[0]))
    utxos.add(transaction.txid(), 1, TxOutput(100, "other"))
    before = utxos.to_dict()
    with pytest.raises(ValueError, match="overwrite"):
        utxos.add_transaction_outputs(transaction)
    assert utxos.to_dict() == before


def test_applied_outputs_do_not_alias_transaction(funded_transaction):
    transaction, utxos, _ = funded_transaction
    txid = transaction.txid()
    utxos.apply_valid_transaction(transaction)
    transaction.outputs[0].amount = 100
    assert not utxos.exists("funding", 0)
    assert utxos.get(txid, 0).amount == 9
