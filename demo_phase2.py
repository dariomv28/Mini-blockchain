from crypto.address import public_key_to_address
from crypto.hash import sha256_hex
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


def main():

    # ========================================
    # 1. CREATE ALICE AND BOB
    # ========================================

    alice_private = generate_private_key()

    alice_public = get_public_key(
        alice_private
    )

    alice_address = public_key_to_address(
        alice_public
    )

    bob_private = generate_private_key()

    bob_public = get_public_key(
        bob_private
    )

    bob_address = public_key_to_address(
        bob_public
    )

    # ========================================
    # 2. CREATE UTXO SET
    # ========================================

    utxos = UTXOSet()

    funding_txid = sha256_hex(
        b"phase2-demo-funding"
    )

    # Giả lập Alice đã có 10 PYC.
    utxos.add(
        funding_txid,
        0,
        TxOutput(
            amount=10,
            recipient_address=alice_address,
        ),
    )

    print(
        "=== PHASE 2 - TRANSACTION DEMO ==="
    )

    print()
    print("Alice:", alice_address)
    print("Bob:  ", bob_address)

    print()
    print("=== INITIAL UTXO ===")

    print(
        "Alice balance:",
        utxos.get_balance(
            alice_address
        ),
        "PYC",
    )

    print(
        "Bob balance:",
        utxos.get_balance(
            bob_address
        ),
        "PYC",
    )

    # ========================================
    # 3. BUILD TRANSACTION
    # ========================================

    transaction = Transaction(
        inputs=[
            TxInput(
                previous_tx_id=funding_txid,
                output_index=0,
            )
        ],

        outputs=[
            # Bob nhận 6.
            TxOutput(
                amount=6,
                recipient_address=bob_address,
            ),

            # Alice nhận lại 3.
            TxOutput(
                amount=3,
                recipient_address=alice_address,
            ),
        ],
    )

    # ========================================
    # 4. SIGN
    # ========================================

    transaction.sign_input(
        0,
        alice_private,
    )

    print()
    print("=== TRANSACTION ===")

    print(
        "Input:",
        f"{funding_txid}:0",
    )

    print("6 PYC -> Bob")
    print("3 PYC -> Alice")

    print(
        "Fee:",
        calculate_transaction_fee(
            transaction,
            utxos,
        ),
        "PYC",
    )

    print(
        "Transaction ID:",
        transaction.txid(),
    )

    # ========================================
    # 5. VALIDATE
    # ========================================

    print()
    print("=== VALIDATION ===")

    valid = validate_transaction(
        transaction,
        utxos,
    )

    print(
        "Valid:",
        valid,
    )

    # ========================================
    # 6. APPLY
    # ========================================

    if valid:
        utxos.apply_valid_transaction(
            transaction
        )

    print()
    print("=== APPLY ===")

    print(
        "Alice balance:",
        utxos.get_balance(
            alice_address
        ),
        "PYC",
    )

    print(
        "Bob balance:",
        utxos.get_balance(
            bob_address
        ),
        "PYC",
    )

    # ========================================
    # 7. DOUBLE SPEND
    # ========================================

    print()
    print(
        "=== DOUBLE SPEND TEST ==="
    )

    valid_again = validate_transaction(
        transaction,
        utxos,
    )

    print(
        "Second transaction valid:",
        valid_again,
    )


if __name__ == "__main__":
    main()
