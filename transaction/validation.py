from ecdsa.errors import MalformedPointError

from crypto.address import public_key_to_address, validate_address
from crypto.keys import public_key_from_hex
from crypto.signature import verify_signature
from transaction.transaction import Transaction
from transaction.tx_input import TxInput
from transaction.tx_output import TxOutput
from transaction.utxo import UTXOSet


def _is_valid_output(output: TxOutput) -> bool:
    return (
        isinstance(output, TxOutput)
        and isinstance(output.amount, int)
        and not isinstance(output.amount, bool)
        and output.amount > 0
        and validate_address(output.recipient_address)
    )


def _validated_fee(transaction: Transaction, utxo_set: UTXOSet) -> int | None:
    """Return the fee only after all regular-transaction rules succeed."""
    if not isinstance(transaction, Transaction) or not isinstance(utxo_set, UTXOSet):
        return None

    if (
        not isinstance(transaction.version, int)
        or isinstance(transaction.version, bool)
        or transaction.version != 1
        or not isinstance(transaction.timestamp, int)
        or isinstance(transaction.timestamp, bool)
        or transaction.timestamp < 0
        or not isinstance(transaction.inputs, list)
        or not transaction.inputs
        or not isinstance(transaction.outputs, list)
        or not transaction.outputs
    ):
        return None

    if not all(_is_valid_output(output) for output in transaction.outputs):
        return None

    # Check every input before serializing the transaction for any signature.
    seen_outpoints = set()
    for tx_input in transaction.inputs:
        if (
            not isinstance(tx_input, TxInput)
            or not isinstance(tx_input.previous_tx_id, str)
            or not tx_input.previous_tx_id
            or not isinstance(tx_input.output_index, int)
            or isinstance(tx_input.output_index, bool)
            or tx_input.output_index < 0
            or not isinstance(tx_input.public_key, str)
            or not tx_input.public_key
            or not isinstance(tx_input.signature, str)
            or not tx_input.signature
        ):
            return None

        outpoint = (tx_input.previous_tx_id, tx_input.output_index)
        if outpoint in seen_outpoints:
            return None
        seen_outpoints.add(outpoint)

    total_input = 0
    for input_index, tx_input in enumerate(transaction.inputs):
        utxo = utxo_set.get(tx_input.previous_tx_id, tx_input.output_index)
        if not _is_valid_output(utxo):
            return None

        public_key = public_key_from_hex(tx_input.public_key)
        signature = bytes.fromhex(tx_input.signature)
        if public_key_to_address(public_key) != utxo.recipient_address:
            return None
        if not verify_signature(
            public_key, transaction.signing_bytes(input_index), signature
        ):
            return None
        total_input += utxo.amount

    fee = total_input - sum(output.amount for output in transaction.outputs)
    return fee if fee >= 0 else None


def _safe_validated_fee(transaction: Transaction, utxo_set: UTXOSet) -> int | None:
    try:
        return _validated_fee(transaction, utxo_set)
    except (
        AttributeError,
        IndexError,
        KeyError,
        TypeError,
        ValueError,
        MalformedPointError,
    ):
        # Malformed external data is invalid, never an accepted transaction.
        return None


def calculate_transaction_fee(transaction: Transaction, utxo_set: UTXOSet) -> int:
    fee = _safe_validated_fee(transaction, utxo_set)
    if fee is None:
        raise ValueError("Cannot calculate fee for an invalid transaction")
    return fee


def validate_transaction(transaction: Transaction, utxo_set: UTXOSet) -> bool:
    """Validate structure, ownership, signatures and value against a UTXO view."""
    return _safe_validated_fee(transaction, utxo_set) is not None
