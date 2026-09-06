from blockchain.block import Block


GENESIS_PREVIOUS_HASH = "0" * 64
GENESIS_TIMESTAMP = 1_788_652_800
GENESIS_VERSION = 1
GENESIS_DIFFICULTY = 1
GENESIS_NONCE = 0

# Giá trị cố định tính bằng serialization và SHA-256 của Phase 3.
GENESIS_HASH = (
    "14c5baf99007aba3bca5d4a32a5dd213"
    "4495a6bdaef5586f515d0f838b654e6a"
)


def create_genesis_block() -> Block:
    block = Block(
        transactions=[],
        previous_block_hash=GENESIS_PREVIOUS_HASH,
        timestamp=GENESIS_TIMESTAMP,
        version=GENESIS_VERSION,
        difficulty=GENESIS_DIFFICULTY,
        nonce=GENESIS_NONCE,
    )

    if block.hash() != GENESIS_HASH:
        raise RuntimeError(
            "Genesis hash differs from the configured network"
        )

    return block


def is_genesis_block(block: Block) -> bool:
    if not isinstance(block, Block):
        return False

    if not isinstance(block.transactions, list):
        return False

    if block.transactions:
        return False

    try:
        return block.hash() == GENESIS_HASH
    except (AttributeError, TypeError, ValueError, OverflowError):
        return False
