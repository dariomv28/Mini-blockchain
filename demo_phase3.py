from blockchain.block import Block

from crypto.address import (
    public_key_to_address,
)
from crypto.hash import sha256_hex
from crypto.keys import (
    generate_private_key,
    get_public_key,
)

from transaction.transaction import (
    Transaction,
)
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
    # 2. SEED ALICE WITH 10 PYC
    # ========================================

    utxos = UTXOSet()

    funding_txid = sha256_hex(
        b"phase3-demo-funding"
    )

    utxos.add(
        funding_txid,
        0,
        TxOutput(
            amount=10,
            recipient_address=alice_address,
        ),
    )

    # ========================================
    # 3. TX1: ALICE -> BOB
    # ========================================

    tx1 = Transaction(
        inputs=[
            TxInput(
                previous_tx_id=funding_txid,
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
    )

    tx1.sign_input(
        0,
        alice_private,
    )

    tx1_valid = validate_transaction(
        tx1,
        utxos,
    )

    if not tx1_valid:
        raise RuntimeError(
            "TX1 should be valid"
        )

    tx1_fee = calculate_transaction_fee(
        tx1,
        utxos,
    )

    utxos.apply_valid_transaction(
        tx1
    )

    # ========================================
    # 4. TX2: BOB -> ALICE
    # ========================================

    tx2 = Transaction(
        inputs=[
            TxInput(
                previous_tx_id=tx1.txid(),
                output_index=0,
            )
        ],
        outputs=[
            TxOutput(
                amount=5,
                recipient_address=alice_address,
            )
        ],
    )

    tx2.sign_input(
        0,
        bob_private,
    )

    tx2_valid = validate_transaction(
        tx2,
        utxos,
    )

    if not tx2_valid:
        raise RuntimeError(
            "TX2 should be valid"
        )

    tx2_fee = calculate_transaction_fee(
        tx2,
        utxos,
    )

    # ========================================
    # 5. CREATE BLOCK
    # ========================================

    previous_block_hash = "0" * 64

    block = Block(
        transactions=[tx1, tx2],
        previous_block_hash=(
            previous_block_hash
        ),
        difficulty=1,
        nonce=0,
    )

    # ========================================
    # 6. PRINT BLOCK DATA
    # ========================================

    print(
        "=== PHASE 3 - BLOCK DEMO ==="
    )

    print()
    print("Alice:", alice_address)
    print("Bob:  ", bob_address)

    print()
    print("=== TRANSACTIONS ===")

    print("TX1 valid:", tx1_valid)
    print("TX1 fee:  ", tx1_fee, "PYC")
    print("TX1 id:   ", tx1.txid())

    print()

    print("TX2 valid:", tx2_valid)
    print("TX2 fee:  ", tx2_fee, "PYC")
    print("TX2 id:   ", tx2.txid())

    print()
    print("=== BLOCK ===")

    print(
        "Previous block hash:",
        block.previous_block_hash,
    )

    print(
        "Merkle root:",
        block.merkle_root,
    )

    print(
        "Timestamp:",
        block.timestamp,
    )

    print(
        "Difficulty:",
        block.difficulty,
    )

    print(
        "Nonce:",
        block.nonce,
    )

    original_hash = block.hash()

    print(
        "Block hash:",
        original_hash,
    )

    # ========================================
    # 7. PROVE NONCE AFFECTS HASH
    # ========================================

    print()
    print("=== NONCE TEST ===")

    block.nonce += 1

    new_hash = block.hash()

    print("New nonce:", block.nonce)
    print("New hash: ", new_hash)

    print(
        "Hash changed:",
        original_hash != new_hash,
    )


if __name__ == "__main__":
    main()
