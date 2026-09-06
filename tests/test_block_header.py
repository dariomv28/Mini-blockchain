from blockchain.block_header import (
    BlockHeader,
)


def make_header() -> BlockHeader:
    return BlockHeader(
        version=1,
        previous_block_hash="0" * 64,
        merkle_root="1" * 64,
        timestamp=1234567890,
        difficulty=1,
        nonce=0,
    )


def test_same_header_has_same_hash():
    header_a = make_header()
    header_b = make_header()

    assert (
        header_a.to_bytes()
        == header_b.to_bytes()
    )

    assert (
        header_a.hash()
        == header_b.hash()
    )


def test_header_hash_is_64_hex_chars():
    block_hash = make_header().hash()

    assert len(block_hash) == 64
    int(block_hash, 16)


def test_nonce_changes_header_hash():
    header = make_header()

    old_hash = header.hash()

    header.nonce = 1

    new_hash = header.hash()

    assert old_hash != new_hash


def test_previous_hash_changes_header_hash():
    header = make_header()
    old_hash = header.hash()

    header.previous_block_hash = "f" * 64

    assert header.hash() != old_hash


def test_merkle_root_changes_header_hash():
    header = make_header()
    old_hash = header.hash()

    header.merkle_root = "a" * 64

    assert header.hash() != old_hash


def test_timestamp_changes_header_hash():
    header = make_header()
    old_hash = header.hash()

    header.timestamp += 1

    assert header.hash() != old_hash


def test_difficulty_changes_header_hash():
    header = make_header()
    old_hash = header.hash()

    header.difficulty += 1

    assert header.hash() != old_hash
