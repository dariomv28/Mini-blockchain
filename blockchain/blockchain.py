from copy import deepcopy

from blockchain.block import Block
from blockchain.genesis import create_genesis_block
from blockchain.validation import (
    validate_block,
    validate_chain as validate_block_sequence,
)


class Blockchain:

    def __init__(self) -> None:
        self._blocks: list[Block] = [create_genesis_block()]

    def __len__(self) -> int:
        return len(self._blocks)

    @property
    def height(self) -> int:
        return len(self._blocks) - 1

    @property
    def chain(self) -> list[Block]:
        return deepcopy(self._blocks)

    def get_latest_block(self) -> Block:
        return deepcopy(self._blocks[-1])

    def get_block_by_height(self, height: int) -> Block | None:
        if type(height) is not int:
            return None

        if height < 0 or height >= len(self._blocks):
            return None

        return deepcopy(self._blocks[height])

    def get_block_by_hash(self, block_hash: str) -> Block | None:
        for block in self._blocks:
            if block.hash() == block_hash:
                return deepcopy(block)

        return None

    def add_block(
        self,
        block: Block,
        *,
        current_time: int | None = None,
    ) -> bool:
        if not isinstance(block, Block):
            return False

        candidate = deepcopy(block)

        if not validate_block(
            candidate,
            self._blocks[-1],
            current_time=current_time,
        ):
            return False

        candidate_hash = candidate.hash()

        if any(
            existing.hash() == candidate_hash
            for existing in self._blocks
        ):
            return False

        self._blocks.append(candidate)
        return True

    def validate_chain(
        self,
        *,
        current_time: int | None = None,
    ) -> bool:
        return validate_block_sequence(
            self._blocks,
            current_time=current_time,
        )
