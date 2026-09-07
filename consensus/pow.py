from blockchain.block import Block
from consensus.difficulty import is_valid_difficulty, target_from_difficulty

MAX_NONCE = (1 << 32) - 1

def is_valid_nonce(nonce: object) -> bool:
    return type(nonce) is int and 0 <= nonce <= MAX_NONCE

def _is_hash(value: object) -> bool:
    return (
        isinstance(value, str)
        and len(value) == 64
        and all(character in "0123456789abcdef" for character in value)
    )


def hash_meets_target(block_hash: object, difficulty: object) -> bool:
    if not _is_hash(block_hash) or not is_valid_difficulty(difficulty):
        return False
    return int(block_hash, 16) < target_from_difficulty(difficulty)


def validate_proof_of_work(block: Block) -> bool:
    if not isinstance(block, Block):
        return False
    if not is_valid_nonce(block.nonce):
        return False

    try:
        return hash_meets_target(block.hash(), block.difficulty)
    except (AttributeError, TypeError, ValueError, OverflowError):
        return False
