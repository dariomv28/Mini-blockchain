"""Strict canonical codecs that preserve the existing signed representation.

Decoding checks shapes and block structure, not signatures, input ownership or
PoW. Loading the ledger must still replay consensus validation; loading pending
transactions must still validate them against the recovered chain and pool.
"""

import json

from blockchain.block import Block
from blockchain.validation import validate_block_structure
from crypto.address import validate_address
from crypto.hash import serialize
from storage.errors import StorageCorruptionError
from transaction.transaction import Transaction
from transaction.tx_input import TxInput
from transaction.tx_output import TxOutput


_TRANSACTION_KEYS = {"version", "inputs", "outputs", "timestamp"}
_INPUT_KEYS = {"previous_tx_id", "output_index", "public_key", "signature"}
_OUTPUT_KEYS = {"amount", "recipient_address"}
_HEADER_KEYS = {
    "version", "previous_block_hash", "merkle_root", "timestamp", "difficulty", "nonce"
}
_MALFORMED_ERRORS = (
    AttributeError, IndexError, KeyError, TypeError, ValueError, OverflowError,
    RecursionError,
)


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise StorageCorruptionError(message)


def _object(value: object, keys: set[str], name: str) -> dict:
    _require(type(value) is dict, f"{name} must be an object")
    _require(set(value) == keys, f"{name} has missing or unexpected fields")
    return value


def _integer(value: object, name: str, minimum: int = 0) -> int:
    _require(type(value) is int and value >= minimum, f"{name} must be an integer >= {minimum}")
    return value


def _string(value: object, name: str) -> str:
    _require(type(value) is str and bool(value), f"{name} must be a nonempty string")
    return value


def _unique_object(pairs: list[tuple[str, object]]) -> dict:
    result = {}
    for key, value in pairs:
        _require(key not in result, f"Duplicate JSON key: {key}")
        result[key] = value
    return result


def _reject_number(value: str) -> None:
    raise StorageCorruptionError("Floating-point and non-finite JSON numbers are not supported")


def _parse(data: bytes) -> object:
    _require(type(data) is bytes, "Canonical payload must be bytes")
    return json.loads(
        data.decode("utf-8"),
        object_pairs_hook=_unique_object,
        parse_float=_reject_number,
        parse_constant=_reject_number,
    )


def _transaction_from_dict(value: object) -> Transaction:
    data = _object(value, _TRANSACTION_KEYS, "Transaction")
    version = _integer(data["version"], "Transaction.version", 1)
    _require(version == 1, "Unsupported transaction version")
    timestamp = _integer(data["timestamp"], "Transaction.timestamp")
    _require(type(data["inputs"]) is list, "Transaction.inputs must be a list")
    _require(type(data["outputs"]) is list and bool(data["outputs"]), "Transaction.outputs must be a nonempty list")

    inputs = []
    for item in data["inputs"]:
        tx_input = _object(item, _INPUT_KEYS, "Input")
        inputs.append(TxInput(
            previous_tx_id=_string(tx_input["previous_tx_id"], "Input.previous_tx_id"),
            output_index=_integer(tx_input["output_index"], "Input.output_index"),
            public_key=_string(tx_input["public_key"], "Input.public_key"),
            signature=_string(tx_input["signature"], "Input.signature"),
        ))

    outputs = []
    for item in data["outputs"]:
        tx_output = _object(item, _OUTPUT_KEYS, "Output")
        amount = _integer(tx_output["amount"], "Output.amount", 1)
        address = _string(tx_output["recipient_address"], "Output.recipient_address")
        _require(validate_address(address), "Output.recipient_address is invalid")
        outputs.append(TxOutput(amount=amount, recipient_address=address))

    # Empty inputs are the existing coinbase representation. Whether it belongs
    # at a block position or in the mempool is checked by the corresponding layer.
    _require(bool(inputs) or len(outputs) == 1, "Coinbase must contain one output")
    return Transaction(inputs=inputs, outputs=outputs, timestamp=timestamp, version=version)


def _transaction_data(transaction: Transaction) -> dict:
    _require(isinstance(transaction, Transaction), "Expected a Transaction")
    # to_dict() uses comprehensions and would otherwise hide tuple inputs/outputs
    # or objects impersonating the nested dataclasses.
    _require(type(transaction.inputs) is list, "Transaction.inputs must be a list")
    _require(type(transaction.outputs) is list, "Transaction.outputs must be a list")
    _require(all(isinstance(item, TxInput) for item in transaction.inputs), "Expected TxInput objects")
    _require(all(isinstance(item, TxOutput) for item in transaction.outputs), "Expected TxOutput objects")
    data = transaction.to_dict()
    _transaction_from_dict(data)
    return data


def _block_from_dict(value: object) -> Block:
    data = _object(value, {"header", "transactions"}, "Block")
    header = _object(data["header"], _HEADER_KEYS, "Header")
    for field in ("version", "timestamp", "difficulty", "nonce"):
        _integer(header[field], f"Header.{field}")
    for field in ("previous_block_hash", "merkle_root"):
        _string(header[field], f"Header.{field}")
    _require(type(data["transactions"]) is list, "Block.transactions must be a list")
    block = Block(
        transactions=[_transaction_from_dict(item) for item in data["transactions"]],
        previous_block_hash=header["previous_block_hash"],
        timestamp=header["timestamp"],
        version=header["version"],
        difficulty=header["difficulty"],
        nonce=header["nonce"],
    )
    # Block.__post_init__ computes a root. Compare it with the persisted root;
    # silently dropping that field would repair tampering during deserialization.
    _require(block.merkle_root == header["merkle_root"], "Stored Merkle root does not match transactions")
    _require(validate_block_structure(block), "Block structure is invalid")
    return block


def encode_transaction(transaction: Transaction) -> bytes:
    """Encode signed transaction structure without checking its ledger inputs."""
    try:
        return serialize(_transaction_data(transaction))
    except _MALFORMED_ERRORS as error:
        raise StorageCorruptionError("Cannot encode transaction") from error


def decode_transaction(data: bytes) -> Transaction:
    """Read exact canonical signed transaction bytes without normalizing fields."""
    try:
        transaction = _transaction_from_dict(_parse(data))
        _require(serialize(transaction.to_dict()) == data, "Transaction payload is not canonical")
        return transaction
    except _MALFORMED_ERRORS as error:
        raise StorageCorruptionError("Cannot decode transaction") from error


def encode_block(block: Block) -> bytes:
    """Encode a structurally checked block, including every signed transaction."""
    try:
        _require(isinstance(block, Block), "Expected a Block")
        _require(type(block.transactions) is list, "Block.transactions must be a list")
        for transaction in block.transactions:
            _transaction_data(transaction)
        data = block.to_dict()
        _block_from_dict(data)
        return serialize(data)
    except _MALFORMED_ERRORS as error:
        raise StorageCorruptionError("Cannot encode block") from error


def decode_block(data: bytes) -> Block:
    """Read canonical block data; the caller must still perform chain replay."""
    try:
        block = _block_from_dict(_parse(data))
        _require(serialize(block.to_dict()) == data, "Block payload is not canonical")
        return block
    except _MALFORMED_ERRORS as error:
        raise StorageCorruptionError("Cannot decode block") from error


def encode_amount(amount: int) -> str:
    """Represent a positive Python integer as exact ASCII decimal TEXT."""
    try:
        _integer(amount, "Amount", 1)
        return str(amount)
    except _MALFORMED_ERRORS as error:
        raise StorageCorruptionError("Cannot encode amount") from error


def decode_amount(data: str) -> int:
    """Reject signs, whitespace, leading zeros and non-ASCII decimal digits."""
    try:
        _require(
            type(data) is str and bool(data) and "1" <= data[0] <= "9"
            and all("0" <= character <= "9" for character in data),
            "Amount must be a canonical positive ASCII decimal string",
        )
        return int(data)
    except _MALFORMED_ERRORS as error:
        raise StorageCorruptionError("Cannot decode amount") from error
