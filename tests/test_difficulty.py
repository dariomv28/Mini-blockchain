import pytest

from consensus.difficulty import (
    MAX_DIFFICULTY,
    MAX_TARGET,
    MINING_DIFFICULTY,
    expected_difficulty,
    is_valid_difficulty,
    target_from_difficulty,
)


def test_target_uses_an_exclusive_integer_threshold():
    assert target_from_difficulty(1) == MAX_TARGET
    assert target_from_difficulty(2) == MAX_TARGET // 2
    assert target_from_difficulty(MINING_DIFFICULTY) == (
        MAX_TARGET // MINING_DIFFICULTY
    )
    assert target_from_difficulty(MAX_DIFFICULTY) == 1


@pytest.mark.parametrize(
    "difficulty",
    [0, -1, True, 1.5, MAX_DIFFICULTY + 1],
)
def test_invalid_difficulty_is_rejected(difficulty):
    assert not is_valid_difficulty(difficulty)

    with pytest.raises(ValueError):
        target_from_difficulty(difficulty)


def test_phase_five_policy_has_a_fixed_non_genesis_difficulty():
    assert expected_difficulty(1) == MINING_DIFFICULTY
    assert expected_difficulty(MINING_DIFFICULTY) == MINING_DIFFICULTY

    with pytest.raises(ValueError):
        expected_difficulty(True)
