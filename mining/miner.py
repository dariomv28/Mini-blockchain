from copy import deepcopy

from blockchain.block import Block
from consensus.difficulty import is_valid_difficulty
from consensus.pow import MAX_NONCE, is_valid_nonce, validate_proof_of_work

def mine_block(
    block: Block,
    *,
    start_nonce: int = 0,
    max_nonce: int = MAX_NONCE,
) -> Block | None:
    if not isinstance(block, Block):
        raise TypeError("block must be a Block")

    if not is_valid_difficulty(block.difficulty):
        raise ValueError("block.difficulty must be a valid difficulty")

    if not is_valid_nonce(start_nonce) or not is_valid_nonce(max_nonce):
        raise ValueError("nonce bounds must be unsigned 32-bit integers")

    if start_nonce > max_nonce:
        raise ValueError("start_nonce cannot be greater than max_nonce")

    candidate = deepcopy(block)

    for nonce in range(start_nonce, max_nonce + 1):
        candidate.nonce = nonce

        if validate_proof_of_work(candidate):
            return candidate

    return None
