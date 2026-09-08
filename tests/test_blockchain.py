from copy import deepcopy

import pytest

from blockchain.blockchain import Blockchain
from blockchain.genesis import GENESIS_HASH, GENESIS_TIMESTAMP
from blockchain.validation import validate_chain
from consensus.pow import validate_proof_of_work
from crypto.address import public_key_to_address
from crypto.keys import generate_private_key, get_public_key
from mining.miner import mine_block


NOW = GENESIS_TIMESTAMP + 100


def make_address() -> str:
    private_key = generate_private_key()
    return public_key_to_address(get_public_key(private_key))


def make_candidate(chain: Blockchain):
    tip = chain.get_latest_block()
    template = chain.create_block_template(
        make_address(),
        timestamp=tip.timestamp + 1,
    )
    candidate = mine_block(template, max_nonce=100_000)
    assert candidate is not None
    return candidate


def make_proof_invalid(block) -> None:
    block.nonce += 1

    while validate_proof_of_work(block):
        block.nonce += 1


def test_new_chain_contains_only_the_fixed_genesis():
    chain = Blockchain()

    assert len(chain) == 1
    assert chain.height == 0
    assert chain.get_latest_block().hash() == GENESIS_HASH
    assert chain.validate_chain(current_time=NOW)


def test_add_mined_blocks_and_lookup():
    chain = Blockchain()
    first = make_candidate(chain)
    assert chain.add_block(first, current_time=NOW)
    second = make_candidate(chain)
    assert chain.add_block(second, current_time=NOW)

    assert len(chain) == 3
    assert chain.height == 2
    assert chain.get_latest_block().hash() == second.hash()
    assert chain.get_block_by_height(1).hash() == first.hash()
    assert chain.get_block_by_hash(second.hash()).hash() == second.hash()
    assert chain.get_block_by_hash("f" * 64) is None
    assert chain.validate_chain(current_time=NOW)


@pytest.mark.parametrize("height", [-1, 1, True, 1.5])
def test_invalid_height_is_not_a_python_list_index(height):
    chain = Blockchain()
    assert chain.get_block_by_height(height) is None


def test_rejected_block_leaves_chain_unchanged():
    chain = Blockchain()
    before = [block.to_dict() for block in chain.chain]
    candidate = make_candidate(chain)
    candidate.merkle_root = "f" * 64

    assert not chain.add_block(candidate, current_time=NOW)
    assert [block.to_dict() for block in chain.chain] == before
    assert candidate.merkle_root == "f" * 64


def test_unmined_or_wrong_difficulty_block_leaves_chain_unchanged():
    chain = Blockchain()
    before = chain.chain
    unmined = make_candidate(chain)
    make_proof_invalid(unmined)

    assert not chain.add_block(unmined, current_time=NOW)
    assert chain.chain == before

    wrong_difficulty = make_candidate(chain)
    wrong_difficulty.difficulty = 1
    wrong_difficulty = mine_block(wrong_difficulty)
    assert wrong_difficulty is not None

    assert not chain.add_block(wrong_difficulty, current_time=NOW)
    assert chain.chain == before


def test_same_block_cannot_be_added_twice():
    chain = Blockchain()
    candidate = make_candidate(chain)

    assert chain.add_block(candidate, current_time=NOW)
    assert not chain.add_block(candidate, current_time=NOW)
    assert len(chain) == 2


def test_block_for_old_tip_is_rejected():
    chain = Blockchain()
    first = make_candidate(chain)
    competing = make_candidate(chain)

    assert chain.add_block(first, current_time=NOW)
    assert not chain.add_block(competing, current_time=NOW)
    assert chain.height == 1


def test_genesis_cannot_be_added_again():
    chain = Blockchain()

    assert not chain.add_block(chain.get_latest_block(), current_time=NOW)
    assert chain.height == 0


def test_mutating_original_candidate_cannot_change_stored_block():
    chain = Blockchain()
    candidate = make_candidate(chain)
    expected = deepcopy(candidate.to_dict())
    assert chain.add_block(candidate, current_time=NOW)

    candidate.nonce += 1
    candidate.transactions[0].outputs[0].amount = 999
    candidate.transactions.clear()

    assert chain.get_latest_block().to_dict() == expected
    assert chain.validate_chain(current_time=NOW)


def test_getters_return_independent_nested_data():
    chain = Blockchain()
    candidate = make_candidate(chain)
    assert chain.add_block(candidate, current_time=NOW)

    for copy in [
        chain.get_latest_block(),
        chain.get_block_by_height(1),
        chain.get_block_by_hash(candidate.hash()),
        chain.chain[1],
    ]:
        copy.transactions[0].outputs[0].amount = 999
        copy.nonce += 1

    detached_list = chain.chain
    detached_list.clear()
    assert len(chain) == 2
    assert chain.get_latest_block().transactions[0].outputs[0].amount == 50
    assert chain.validate_chain(current_time=NOW)


def test_chain_instances_do_not_share_genesis():
    first = Blockchain()
    second = Blockchain()
    assert first.add_block(make_candidate(first), current_time=NOW)

    assert first.height == 1
    assert second.height == 0
    assert second.get_latest_block().hash() == GENESIS_HASH


def test_tampered_snapshot_does_not_damage_the_live_chain():
    chain = Blockchain()
    for _ in range(2):
        assert chain.add_block(make_candidate(chain), current_time=NOW)

    snapshot = chain.chain
    make_proof_invalid(snapshot[1])

    assert not validate_chain(snapshot, current_time=NOW)
    assert chain.validate_chain(current_time=NOW)
