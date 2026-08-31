from ecdsa.errors import MalformedPointError

from crypto.address import (
    public_key_to_address,
    validate_address,
)
from crypto.keys import public_key_from_hex
from crypto.signature import verify_signature

from transaction.transaction import Transaction
from transaction.utxo import UTXOSet


def calculate_transaction_fee(
    transaction: Transaction,
    utxo_set: UTXOSet,
) -> int:

    total_input = 0

    for tx_input in transaction.inputs:
        utxo = utxo_set.get(
            tx_input.previous_tx_id,
            tx_input.output_index,
        )

        if utxo is None:
            raise ValueError(
                "Referenced UTXO does not exist"
            )

        total_input += utxo.amount

    total_output = sum(
        output.amount
        for output in transaction.outputs
    )

    return total_input - total_output


def validate_transaction(
    transaction: Transaction,
    utxo_set: UTXOSet,
) -> bool:

    # Rule 1:
    # Transaction thường phải có input.
    if not transaction.inputs:
        return False

    # Rule 2:
    # Phải tạo ít nhất một output.
    if not transaction.outputs:
        return False

    # Rule 3 + 4:
    # Kiểm tra amount và address.
    for output in transaction.outputs:

        # bool là subclass của int trong Python,
        # nên phải loại riêng.
        if (
            not isinstance(output.amount, int)
            or isinstance(output.amount, bool)
        ):
            return False

        if output.amount <= 0:
            return False

        if not validate_address(
            output.recipient_address
        ):
            return False

    seen_outpoints = set()

    total_input = 0

    for input_index, tx_input in enumerate(
        transaction.inputs
    ):

        outpoint = (
            tx_input.previous_tx_id,
            tx_input.output_index,
        )

        # Rule 5:
        # Không được dùng cùng UTXO hai lần
        # trong cùng một transaction.
        if outpoint in seen_outpoints:
            return False

        seen_outpoints.add(
            outpoint
        )

        # Rule 6:
        # UTXO phải tồn tại.
        utxo = utxo_set.get(
            *outpoint
        )

        if utxo is None:
            return False

        if (
            not tx_input.public_key
            or not tx_input.signature
        ):
            return False

        # Chuyển public key hex
        # về VerifyingKey.
        try:
            public_key = public_key_from_hex(
                tx_input.public_key
            )

            signature = bytes.fromhex(
                tx_input.signature
            )

        except (
            ValueError,
            TypeError,
            MalformedPointError,
        ):
            return False

        # Rule 7:
        # Public key phải tạo ra đúng address
        # sở hữu UTXO.
        derived_address = (
            public_key_to_address(
                public_key
            )
        )

        if (
            derived_address
            != utxo.recipient_address
        ):
            return False

        # Rule 8:
        # Signature phải hợp lệ.
        signing_bytes = (
            transaction.signing_bytes(
                input_index
            )
        )

        if not verify_signature(
            public_key,
            signing_bytes,
            signature,
        ):
            return False

        # Amount input luôn lấy từ UTXO,
        # KHÔNG lấy từ sender.
        total_input += utxo.amount

    total_output = sum(
        output.amount
        for output in transaction.outputs
    )

    # Rule 9:
    # Không được tạo coin từ không khí.
    if total_input < total_output:
        return False

    return True
