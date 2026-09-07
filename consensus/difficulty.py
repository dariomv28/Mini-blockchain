
MAX_TARGET = 1 << 256
MAX_DIFFICULTY = MAX_TARGET


MINING_DIFFICULTY = 16


def is_valid_difficulty(difficulty: object) -> bool:
    return (
        type(difficulty) is int
        and 1 <= difficulty <= MAX_DIFFICULTY
    )


def target_from_difficulty(difficulty: int) -> int:
    if not is_valid_difficulty(difficulty):
        raise ValueError("difficulty must be an integer from 1 to MAX_DIFFICULTY")

    return MAX_TARGET // difficulty


def expected_difficulty(previous_difficulty: int) -> int:

    if not is_valid_difficulty(previous_difficulty):
        raise ValueError("previous_difficulty must be a valid difficulty")

    return MINING_DIFFICULTY
