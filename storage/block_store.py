"""Block row helpers; the facade owns the shared connection transaction."""

import sqlite3

from blockchain.block import Block
from storage.codec import decode_block, encode_block
from storage.database import MAX_SQLITE_INTEGER
from storage.errors import StorageCorruptionError, StorageError


def encode_block_row(height: int, block: Block) -> tuple[int, str, str, bytes]:
    if type(height) is not int or not 0 <= height <= MAX_SQLITE_INTEGER:
        raise StorageError("Block height exceeds SQLite integer storage bounds")
    data = encode_block(block)
    return height, block.hash(), block.previous_block_hash, data


def insert_block_row(connection: sqlite3.Connection, row: tuple) -> None:
    connection.execute(
        "INSERT INTO blocks(height, hash, previous_hash, data) VALUES (?, ?, ?, ?)",
        row,
    )


def read_block_rows(connection: sqlite3.Connection) -> list[Block]:
    rows = connection.execute(
        "SELECT height, hash, previous_hash, data FROM blocks ORDER BY height"
    ).fetchall()
    if not rows:
        raise StorageCorruptionError("Database contains no genesis block")
    blocks = []
    for expected_height, (height, block_hash, previous_hash, data) in enumerate(rows):
        if type(height) is not int or height != expected_height:
            raise StorageCorruptionError("Block heights are not contiguous from zero")
        block = decode_block(data)
        if block_hash != block.hash() or previous_hash != block.previous_block_hash:
            raise StorageCorruptionError(f"Block indexes disagree with payload at height {height}")
        blocks.append(block)
    return blocks
