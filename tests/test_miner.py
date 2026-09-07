from copy import deepcopy

import pytest

from blockchain.block import Block
from blockchain.genesis import create_genesis_block
from consensus.difficulty import MINING_DIFFICULTY
from consensus.pow import MAX_NONCE, validate_proof_of_work
from crypto.address import public_key_to_address
from crypto.keys import generate_private_key, get_public_key
from mining.block_template import create_block_template
from mining.coinbase import validate_coinbase_transaction
from mining.miner import mine_block


def make_address() -> str:
    private_key = generate_private_key()
    return public_key_to_address(get_public_key(private_key))


def test_template_has_coinbase_first_and_the_network_difficulty():
    genesis = create_genesis_block()
    template = create_block_template(
        genesis,
        make_address(),
        timestamp=genesis.timestamp + 1,
    )

    assert template.previous_block_hash == genesis.hash()
    assert template.difficulty == MINING_DIFFICULTY
    assert len(template.transactions) == 1
    assert validate_coinbase_transaction(
        template.transactions[0],
        block_timestamp=template.timestamp,
    )


def test_mining_returns_a_distinct_valid_copy_without_mutating_template():
    template = Block(
        transactions=[],
        previous_block_hash="0" * 64,
        timestamp=100,
        difficulty=2,
    )
    before = deepcopy(template.to_dict())

    mined = mine_block(template, max_nonce=10_000)

    assert mined is not None
    assert mined is not template
    assert validate_proof_of_work(mined)
    assert template.to_dict() == before


def test_mining_returns_none_when_a_known_invalid_one_nonce_range_is_exhausted():
    template = Block(
        transactions=[],
        previous_block_hash="0" * 64,
        timestamp=100,
        difficulty=2,
    )

    while validate_proof_of_work(template):
        template.nonce += 1

    assert mine_block(
        template,
        start_nonce=template.nonce,
        max_nonce=template.nonce,
    ) is None


def test_miner_rejects_invalid_nonce_bounds():
    template = Block(
        transactions=[],
        previous_block_hash="0" * 64,
        timestamp=100,
        difficulty=2,
    )

    with pytest.raises(ValueError):
        mine_block(template, start_nonce=2, max_nonce=1)

    for bounds in [
        {"start_nonce": -1, "max_nonce": 1},
        {"start_nonce": 0, "max_nonce": MAX_NONCE + 1},
        {"start_nonce": True, "max_nonce": 1},
    ]:
        with pytest.raises(ValueError):
            mine_block(template, **bounds)
