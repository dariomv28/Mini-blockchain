
import time

from blockchain.block import Block
from blockchain.chainstate import ChainState, apply_block_transactions
from blockchain.genesis import is_genesis_block
from blockchain.merkle import calculate_merkle_root_from_txids
from consensus.difficulty import (
    expected_difficulty,
    is_valid_difficulty,
)
from consensus.pow import (
    is_valid_nonce,
    validate_proof_of_work,
)
from mining.coinbase import validate_coinbase_structure
from transaction.transaction import Transaction


SUPPORTED_BLOCK_VERSION = 1
MAX_FUTURE_BLOCK_TIME = 2 * 60 * 60


def _is_integer(value: object, minimum: int) -> bool:
    # Loại bool: True không được dùng thay cho version = 1.
    return type(value) is int and value >= minimum


def _is_hash(value: object) -> bool:
    return (
        isinstance(value, str)
        and len(value) == 64
        and all(char in "0123456789abcdef" for char in value)
    )


def _resolve_current_time(current_time: int | None) -> int:
    if current_time is None:
        return int(time.time())

    if not _is_integer(current_time, 0):
        raise ValueError("current_time must be a non-negative integer")

    return current_time


def validate_block_structure(block: Block) -> bool:
    if not isinstance(block, Block):
        return False

    if (
        not _is_integer(block.version, 1)
        or block.version != SUPPORTED_BLOCK_VERSION
    ):
        return False

    if not _is_integer(block.timestamp, 0):
        return False

    if not is_valid_difficulty(block.difficulty):
        return False

    if not is_valid_nonce(block.nonce):
        return False

    if not _is_hash(block.previous_block_hash):
        return False

    if not _is_hash(block.merkle_root):
        return False

    if not isinstance(block.transactions, list):
        return False

    if not all(
        isinstance(transaction, Transaction)
        for transaction in block.transactions
    ):
        return False

    try:
        txids = [transaction.txid() for transaction in block.transactions]

        if not all(_is_hash(txid) for txid in txids):
            return False

        if len(txids) != len(set(txids)):
            return False

        expected_root = calculate_merkle_root_from_txids(txids)
    except (AttributeError, TypeError, ValueError, OverflowError):
        return False

    # So sánh với root đã khai báo, tuyệt đối không ghi đè root đó.
    return block.merkle_root == expected_root


def validate_non_genesis_block_body(block: Block) -> bool:
    """Check coinbase placement/schema; the reward cap requires ledger state."""
    if not isinstance(block, Block):
        return False

    if (
        not isinstance(block.transactions, list)
        or not block.transactions
    ):
        return False

    if not all(
        isinstance(transaction, Transaction)
        for transaction in block.transactions
    ):
        return False

    if not validate_coinbase_structure(
        block.transactions[0],
        block_timestamp=block.timestamp,
    ):
        return False

    # The zero-input representation is reserved exclusively for the first
    # transaction. Full input validation is performed against the ledger later.
    return all(
        isinstance(transaction.inputs, list)
        and bool(transaction.inputs)
        for transaction in block.transactions[1:]
    )


def validate_block_header(
    block: Block,
    previous_block: Block,
    *,
    current_time: int | None = None,
) -> bool:
    """Check structure, link, time, difficulty, PoW and coinbase schema only."""
    now = _resolve_current_time(current_time)

    if not validate_block_structure(previous_block):
        return False

    if not validate_block_structure(block):
        return False

    if block.previous_block_hash != previous_block.hash():
        return False

    # Quy tắc đơn giản của PyChain: cho phép hai block cùng giây.
    if block.timestamp < previous_block.timestamp:
        return False

    if block.timestamp > now + MAX_FUTURE_BLOCK_TIME:
        return False

    if block.difficulty != expected_difficulty(previous_block.difficulty):
        return False

    if not validate_non_genesis_block_body(block):
        return False

    return validate_proof_of_work(block)


def validate_and_apply_block(
    block: Block,
    previous_block: Block,
    *,
    state: ChainState,
    current_time: int | None = None,
) -> ChainState | None:
    """Return the next state on success, without changing the supplied state."""
    if not validate_block_header(block, previous_block, current_time=current_time):
        return None
    if not isinstance(state, ChainState):
        return None
    return apply_block_transactions(block, state)


def validate_block(
    block: Block,
    previous_block: Block,
    *,
    state: ChainState,
    current_time: int | None = None,
) -> bool:
    """Full validation given the trusted parent's ledger state."""
    return validate_and_apply_block(
        block, previous_block, state=state, current_time=current_time
    ) is not None


def rebuild_chain_state(
    blocks: list[Block],
    *,
    current_time: int | None = None,
) -> ChainState | None:
    """Rebuild from the fixed genesis, independently of any cached UTXO state."""
    now = _resolve_current_time(current_time)

    if not isinstance(blocks, list) or not blocks:
        return None

    if not validate_block_structure(blocks[0]):
        return None

    if not is_genesis_block(blocks[0]):
        return None

    seen_hashes = {blocks[0].hash()}
    state = ChainState()

    for index in range(1, len(blocks)):
        block = blocks[index]

        next_state = validate_and_apply_block(
            block,
            blocks[index - 1],
            state=state,
            current_time=now,
        )
        if next_state is None:
            return None

        block_hash = block.hash()

        if block_hash in seen_hashes:
            return None

        seen_hashes.add(block_hash)
        state = next_state

    return state


def validate_chain(
    blocks: list[Block],
    *,
    current_time: int | None = None,
) -> bool:
    """Validate every block and ledger transition from genesis."""
    return rebuild_chain_state(blocks, current_time=current_time) is not None
