from blockchain.block import Block
from consensus.difficulty import target_from_difficulty
from consensus.pow import (
    MAX_NONCE,
    hash_meets_target,
    is_valid_nonce,
    validate_proof_of_work,
)


def make_block(difficulty: int = 2) -> Block:
    return Block(
        transactions=[],
        previous_block_hash="0" * 64,
        timestamp=100,
        difficulty=difficulty,
    )


def find_valid_nonce(block: Block) -> int:
    while not validate_proof_of_work(block):
        block.nonce += 1

    return block.nonce


def test_hash_target_boundaries_and_input_validation():
    assert hash_meets_target("0" * 64, 16)
    assert not hash_meets_target("f" * 64, 16)
    assert hash_meets_target("f" * 64, 1)
    target = target_from_difficulty(2)
    assert hash_meets_target(f"{target - 1:064x}", 2)
    assert not hash_meets_target(f"{target:064x}", 2)
    assert not hash_meets_target("F" * 64, 1)
    assert not hash_meets_target("not-a-hash", 16)
    assert not hash_meets_target("0" * 64, True)


def test_pow_is_rechecked_after_the_nonce_changes():
    block = make_block()
    valid_nonce = find_valid_nonce(block)

    assert validate_proof_of_work(block)

    invalid_nonce = valid_nonce + 1
    block.nonce = invalid_nonce

    while validate_proof_of_work(block):
        invalid_nonce += 1
        block.nonce = invalid_nonce

    assert not validate_proof_of_work(block)


def test_nonce_must_fit_an_unsigned_32_bit_header_field():
    assert is_valid_nonce(0)
    assert is_valid_nonce(MAX_NONCE)
    assert not is_valid_nonce(-1)
    assert not is_valid_nonce(MAX_NONCE + 1)
    assert not is_valid_nonce(True)
