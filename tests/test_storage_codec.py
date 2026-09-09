from copy import deepcopy
import json

import pytest
from ecdsa import SECP256k1, SigningKey

from blockchain.block import Block
from blockchain.genesis import GENESIS_HASH, GENESIS_TIMESTAMP, create_genesis_block
from consensus.pow import MAX_NONCE, validate_proof_of_work
from crypto.address import public_key_to_address
from crypto.hash import serialize
from crypto.signature import sign_message
from mining.coinbase import create_coinbase_transaction
from storage.codec import (
    decode_amount,
    decode_block,
    decode_transaction,
    encode_amount,
    encode_block,
    encode_transaction,
)
from storage.errors import (
    StorageClosedError,
    StorageCommitUncertainError,
    StorageConfigurationError,
    StorageConflictError,
    StorageCorruptionError,
    StorageError,
    StorageVersionError,
)
from transaction.transaction import Transaction
from transaction.tx_input import TxInput
from transaction.tx_output import TxOutput
from transaction.utxo import UTXOSet
from transaction.validation import validate_transaction


KEY = SigningKey.from_secret_exponent(31, curve=SECP256k1)
ADDRESS = public_key_to_address(KEY.get_verifying_key())


@pytest.fixture
def transaction():
    result = Transaction([TxInput("funding-a", 0)], [TxOutput(99, ADDRESS)], timestamp=123)
    result.sign_input(0, KEY)
    return result


@pytest.fixture
def block(transaction):
    coinbase = create_coinbase_transaction(ADDRESS, timestamp=GENESIS_TIMESTAMP + 1)
    return Block(
        transactions=[coinbase, transaction],
        previous_block_hash=GENESIS_HASH,
        timestamp=GENESIS_TIMESTAMP + 1,
        difficulty=16,
        nonce=7,
    )


def test_storage_exception_hierarchy_distinguishes_failure_reasons():
    assert issubclass(StorageError, RuntimeError)
    for error_type in (
        StorageClosedError, StorageCommitUncertainError, StorageConfigurationError,
        StorageConflictError, StorageCorruptionError, StorageVersionError,
    ):
        assert issubclass(error_type, StorageError)
        assert str(error_type("reason")) == "reason"


def test_genesis_round_trip_keeps_fixed_hash_and_empty_transactions():
    genesis = create_genesis_block()
    payload = encode_block(genesis)
    recovered = decode_block(payload)
    assert payload == serialize(genesis.to_dict())
    assert recovered == genesis
    assert recovered.hash() == GENESIS_HASH
    assert recovered.transactions == []


def test_signed_block_round_trip_preserves_full_payload_and_is_independent(block):
    expected = deepcopy(block)
    payload = encode_block(block)
    recovered = decode_block(payload)
    assert payload == serialize(block.to_dict())
    assert recovered.to_dict() == block.to_dict()
    assert recovered.hash() == block.hash()
    assert [tx.txid() for tx in recovered.transactions] == [tx.txid() for tx in block.transactions]
    recovered.transactions[1].inputs[0].signature = "changed"
    recovered.transactions[0].outputs[0].amount = 999
    assert block == expected
    assert decode_block(payload) == expected


def test_transaction_codec_preserves_case_and_non_hash_input_reference(transaction):
    transaction.inputs[0].public_key = transaction.inputs[0].public_key.upper()
    transaction.inputs[0].signature = sign_message(KEY, transaction.signing_bytes(0)).hex().upper()
    utxos = UTXOSet()
    utxos.add("funding-a", 0, TxOutput(100, ADDRESS))
    assert validate_transaction(transaction, utxos)
    payload = encode_transaction(transaction)
    recovered = decode_transaction(payload)
    assert recovered == transaction
    assert recovered.txid() == transaction.txid()
    assert recovered.inputs[0].previous_tx_id == "funding-a"
    assert validate_transaction(recovered, utxos)
    recovered.outputs[0].amount = 1
    assert transaction.outputs[0].amount == 99


def test_coinbase_transaction_round_trip_and_placement_left_to_caller():
    coinbase = create_coinbase_transaction(ADDRESS, timestamp=123)
    recovered = decode_transaction(encode_transaction(coinbase))
    assert recovered == coinbase
    assert recovered.inputs == []
    assert not validate_transaction(recovered, UTXOSet())


def test_large_integers_multiple_inputs_outputs_and_dependencies_round_trip():
    parent = Transaction(
        [TxInput("funding-a", 0), TxInput("funding-b", 2**80)],
        [TxOutput(2**100, ADDRESS), TxOutput(7, ADDRESS)],
        timestamp=2**80,
    )
    for index in range(2):
        parent.sign_input(index, KEY)
    child = Transaction([TxInput(parent.txid(), 0)], [TxOutput(2**100 - 1, ADDRESS)], timestamp=2**80 + 1)
    child.sign_input(0, KEY)
    block = Block([parent, child], GENESIS_HASH, timestamp=2**80, difficulty=2**100)
    recovered = decode_block(encode_block(block))
    assert recovered == block
    assert recovered.transactions[1].inputs[0].previous_tx_id == recovered.transactions[0].txid()
    assert type(recovered.transactions[0].outputs[0].amount) is int
    assert recovered.hash() == block.hash()
    assert decode_transaction(encode_transaction(parent)) == parent


def test_codec_does_not_claim_to_validate_signatures_pow_or_ledger(block):
    block.transactions[1].inputs[0].signature = "invalid-but-nonempty"
    block.refresh_merkle_root()
    while validate_proof_of_work(block):
        block.nonce += 1
    recovered = decode_block(encode_block(block))
    assert recovered == block
    assert not validate_proof_of_work(recovered)
    assert not validate_transaction(recovered.transactions[1], UTXOSet())


@pytest.mark.parametrize("decoder", [decode_block, decode_transaction])
@pytest.mark.parametrize("value", [None, {}, [], "{}", bytearray(b"{}"), memoryview(b"{}")])
def test_decoders_require_bytes(decoder, value):
    with pytest.raises(StorageCorruptionError):
        decoder(value)


@pytest.mark.parametrize("payload", [
    b"", b"\xff", b"{", b"[]", b"null", b"true",
    b'{"timestamp":NaN}', b'{"timestamp":Infinity}', b'{"timestamp":-Infinity}',
    b'{"timestamp":1.0}', b'{"timestamp":1e0}',
    b'{"timestamp":1,"timestamp":1}',
    b'{"inputs":[{"output_index":0,"output_index":0}]}',
])
def test_invalid_json_numbers_duplicates_and_shapes_are_corruption(payload):
    with pytest.raises(StorageCorruptionError):
        decode_transaction(payload)


@pytest.mark.parametrize("defect", ["leading_space", "trailing_newline", "pretty_json", "key_order"])
def test_equivalent_noncanonical_transaction_json_is_rejected(transaction, defect):
    payload = encode_transaction(transaction)
    if defect == "leading_space":
        payload = b" " + payload
    elif defect == "trailing_newline":
        payload += b"\n"
    elif defect == "pretty_json":
        payload = json.dumps(transaction.to_dict(), indent=2).encode()
    else:
        payload = json.dumps(transaction.to_dict(), separators=(",", ":")).encode()
    with pytest.raises(StorageCorruptionError, match="canonical"):
        decode_transaction(payload)


def test_noncanonical_block_bytes_and_duplicate_nested_header_are_rejected(block):
    payload = encode_block(block)
    with pytest.raises(StorageCorruptionError, match="canonical"):
        decode_block(payload + b" ")
    duplicate = payload.replace(b'"nonce":7', b'"nonce":7,"nonce":7', 1)
    with pytest.raises(StorageCorruptionError, match="Duplicate"):
        decode_block(duplicate)


@pytest.mark.parametrize("path", [(), ("inputs", 0), ("outputs", 0)])
@pytest.mark.parametrize("operation", ["missing", "extra"])
def test_exact_keys_required_at_every_transaction_level(transaction, path, operation):
    data = transaction.to_dict()
    target = data
    for key in path:
        target = target[key]
    if operation == "missing":
        del target[next(iter(target))]
    else:
        target["unexpected"] = 1
    with pytest.raises(StorageCorruptionError, match="fields"):
        decode_transaction(serialize(data))


@pytest.mark.parametrize("path,value", [
    (("version",), True), (("version",), 2), (("timestamp",), False),
    (("timestamp",), -1), (("timestamp",), "123"),
    (("inputs",), None), (("outputs",), []),
    (("inputs", 0, "output_index"), True), (("inputs", 0, "output_index"), -1),
    (("inputs", 0, "previous_tx_id"), ""), (("inputs", 0, "public_key"), ""),
    (("inputs", 0, "signature"), ""), (("inputs", 0, "signature"), 123),
    (("outputs", 0, "amount"), True), (("outputs", 0, "amount"), 0),
    (("outputs", 0, "amount"), -1), (("outputs", 0, "recipient_address"), "invalid"),
])
def test_transaction_field_types_and_ranges_are_strict(transaction, path, value):
    data = transaction.to_dict()
    target = data
    for key in path[:-1]:
        target = target[key]
    target[path[-1]] = value
    with pytest.raises(StorageCorruptionError):
        decode_transaction(serialize(data))


def test_zero_input_transaction_requires_coinbase_output_shape():
    invalid = Transaction([], [TxOutput(1, ADDRESS), TxOutput(2, ADDRESS)], timestamp=123)
    with pytest.raises(StorageCorruptionError, match="Coinbase"):
        encode_transaction(invalid)


@pytest.mark.parametrize("field,value", [
    ("version", True), ("version", 2), ("timestamp", -1),
    ("difficulty", 0), ("difficulty", 2**256 + 1),
    ("nonce", False), ("nonce", MAX_NONCE + 1),
    ("previous_block_hash", "ABC"),
])
def test_header_type_and_structure_are_validated(block, field, value):
    data = block.to_dict()
    data["header"][field] = value
    with pytest.raises(StorageCorruptionError):
        decode_block(serialize(data))


@pytest.mark.parametrize("path", [(), ("header",)])
def test_block_and_header_reject_missing_and_unknown_fields(block, path):
    for missing in (False, True):
        data = block.to_dict()
        target = data if not path else data[path[0]]
        if missing:
            del target[next(iter(target))]
        else:
            target["unexpected"] = 1
        with pytest.raises(StorageCorruptionError, match="fields"):
            decode_block(serialize(data))


def test_tampered_merkle_root_is_never_repaired_by_constructor(block):
    data = block.to_dict()
    data["header"]["merkle_root"] = "f" * 64
    with pytest.raises(StorageCorruptionError, match="Merkle"):
        decode_block(serialize(data))
    block.merkle_root = "f" * 64
    before = deepcopy(block)
    with pytest.raises(StorageCorruptionError, match="Merkle"):
        encode_block(block)
    assert block == before


def test_transaction_change_cannot_be_hidden_by_merkle_recomputation(block):
    data = block.to_dict()
    data["transactions"][1]["outputs"][0]["amount"] -= 1
    with pytest.raises(StorageCorruptionError, match="Merkle"):
        decode_block(serialize(data))


def test_duplicate_block_transactions_rejected_even_with_matching_merkle(block):
    block.transactions.append(deepcopy(block.transactions[1]))
    block.refresh_merkle_root()
    with pytest.raises(StorageCorruptionError, match="structure"):
        decode_block(serialize(block.to_dict()))


@pytest.mark.parametrize("encoder", [encode_block, encode_transaction])
@pytest.mark.parametrize("value", [None, {}, [], b"{}"])
def test_encoders_reject_non_model_objects(encoder, value):
    with pytest.raises(StorageCorruptionError):
        encoder(value)


@pytest.mark.parametrize("field", ["inputs", "outputs"])
def test_transaction_encoder_does_not_coerce_tuple_fields_to_list(transaction, field):
    setattr(transaction, field, tuple(getattr(transaction, field)))
    with pytest.raises(StorageCorruptionError):
        encode_transaction(transaction)


def test_block_encoder_does_not_coerce_tuple_transactions(block):
    block.transactions = tuple(block.transactions)
    with pytest.raises(StorageCorruptionError):
        encode_block(block)


@pytest.mark.parametrize("defect", ["input_object", "output_object", "amount_bool", "version_bool"])
def test_transaction_encoder_validates_original_nested_objects(transaction, defect):
    if defect == "input_object":
        transaction.inputs[0] = transaction.inputs[0].to_dict()
    elif defect == "output_object":
        transaction.outputs[0] = transaction.outputs[0].to_dict()
    elif defect == "amount_bool":
        transaction.outputs[0].amount = True
    else:
        transaction.version = True
    with pytest.raises(StorageCorruptionError):
        encode_transaction(transaction)


@pytest.mark.parametrize("amount", [1, 50, 2**63, 2**100, 10**500])
def test_decimal_amount_round_trip_is_exact_for_large_python_integers(amount):
    encoded = encode_amount(amount)
    assert type(encoded) is str
    assert encoded == str(amount)
    assert decode_amount(encoded) == amount
    assert type(decode_amount(encoded)) is int


@pytest.mark.parametrize("amount", [0, -1, True, False, 1.0, "1", None])
def test_amount_encoder_requires_positive_native_integer(amount):
    with pytest.raises(StorageCorruptionError):
        encode_amount(amount)


@pytest.mark.parametrize("data", [
    "", "0", "00", "01", "+1", "-1", " 1", "1 ", "1\n", "1.0", "1e3",
    "\u0661", "\uff11", "1\u0661", "1\x00", 1, b"1", None,
])
def test_decimal_decoder_rejects_noncanonical_or_non_ascii_values(data):
    with pytest.raises(StorageCorruptionError):
        decode_amount(data)
