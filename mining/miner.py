from __future__ import annotations

from copy import deepcopy
import threading
from typing import Any, Callable

from blockchain.block import Block
from consensus.difficulty import is_valid_difficulty
from consensus.pow import MAX_NONCE, is_valid_nonce, validate_proof_of_work


def mine_block(
    block: Block,
    *,
    start_nonce: int = 0,
    max_nonce: int = MAX_NONCE,
) -> Block | None:
    return mine_block_with_progress(
        block,
        start_nonce=start_nonce,
        max_nonce=max_nonce,
    )


def mine_block_with_progress(
    block: Block,
    *,
    start_nonce: int = 0,
    max_nonce: int = MAX_NONCE,
    progress_interval: int = 1000,
    on_progress: Callable[[dict[str, Any]], None] | None = None,
    stop_event: threading.Event | None = None,
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
        if stop_event is not None and stop_event.is_set():
            return None

        candidate.nonce = nonce

        if on_progress is not None and (nonce - start_nonce) % progress_interval == 0:
            on_progress({
                "nonce": nonce,
                "hash": candidate.hash(),
                "hashes_tried": nonce - start_nonce + 1,
            })

        if validate_proof_of_work(candidate):
            if on_progress is not None:
                on_progress({
                    "nonce": nonce,
                    "hash": candidate.hash(),
                    "hashes_tried": nonce - start_nonce + 1,
                })
            return candidate

    return None
