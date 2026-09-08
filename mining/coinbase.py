from crypto.address import validate_address
from transaction.transaction import Transaction
from transaction.tx_output import TxOutput


BLOCK_SUBSIDY = 50
SUPPORTED_TRANSACTION_VERSION = 1


def _is_non_negative_integer(value: object) -> bool:
    return type(value) is int and value >= 0


def create_coinbase_transaction(
    recipient_address: str,
    *,
    timestamp: int,
    fees: int = 0,
) -> Transaction:
    if not validate_address(recipient_address):
        raise ValueError("recipient_address must be a valid PyChain address")

    if not _is_non_negative_integer(timestamp):
        raise ValueError("timestamp must be a non-negative integer")

    if not _is_non_negative_integer(fees):
        raise ValueError("fees must be a non-negative integer")

    return Transaction(
        inputs=[],
        outputs=[
            TxOutput(
                amount=BLOCK_SUBSIDY + fees,
                recipient_address=recipient_address,
            )
        ],
        timestamp=timestamp,
        version=SUPPORTED_TRANSACTION_VERSION,
    )


def is_coinbase_transaction(transaction: object) -> bool:
    return (
        isinstance(transaction, Transaction)
        and isinstance(transaction.inputs, list)
        and not transaction.inputs
    )


def validate_coinbase_structure(
    transaction: object,
    *,
    block_timestamp: int,
) -> bool:
    if not _is_non_negative_integer(block_timestamp):
        return False

    if not is_coinbase_transaction(transaction):
        return False

    if (
        type(transaction.version) is not int
        or transaction.version != SUPPORTED_TRANSACTION_VERSION
    ):
        return False

    if (
        type(transaction.timestamp) is not int
        or transaction.timestamp != block_timestamp
    ):
        return False

    if (
        not isinstance(transaction.outputs, list)
        or len(transaction.outputs) != 1
    ):
        return False

    output = transaction.outputs[0]

    return (
        isinstance(output, TxOutput)
        and type(output.amount) is int
        and output.amount > 0
        and validate_address(output.recipient_address)
    )


def validate_coinbase_transaction(
    transaction: object,
    *,
    block_timestamp: int,
    total_fees: int = 0,
) -> bool:
    """Check the reward cap using fees independently verified by the caller."""
    return (
        _is_non_negative_integer(total_fees)
        and validate_coinbase_structure(transaction, block_timestamp=block_timestamp)
        and transaction.outputs[0].amount <= BLOCK_SUBSIDY + total_fees
    )
