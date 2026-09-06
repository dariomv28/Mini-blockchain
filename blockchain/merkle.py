from crypto.hash import sha256_hex
from transaction.transaction import Transaction


def _combine_hashes(left_hash: str, right_hash: str) -> str:
    left_bytes = bytes.fromhex(left_hash)
    right_bytes = bytes.fromhex(right_hash)
    return sha256_hex(left_bytes + right_bytes)


def calculate_merkle_root_from_txids(txids: list[str]) -> str:
    if not txids:
        return sha256_hex(b"")

    current_level = list(txids)

    while len(current_level) > 1:

        if len(current_level) % 2 == 1:
            current_level.append(current_level[-1])

        next_level = []

        for i in range(0, len(current_level), 2):
            parent_hash = _combine_hashes(
                current_level[i],
                current_level[i + 1],
            )
            next_level.append(parent_hash)

        current_level = next_level

    return current_level[0]


def calculate_merkle_root(transactions: list[Transaction]) -> str:

    txids = [
        transaction.txid()
        for transaction in transactions
    ]

    return calculate_merkle_root_from_txids(txids)
