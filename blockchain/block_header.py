from dataclasses import dataclass
from crypto.hash import serialize, sha256_hex

@dataclass
class BlockHeader:
    version: int
    previous_block_hash: str
    merkle_root: str
    timestamp: int
    difficulty: int
    nonce: int

    def to_dict(self) -> dict:
        return {
            "version": self.version,
            "previous_block_hash": self.previous_block_hash,
            "merkle_root": self.merkle_root,
            "timestamp": self.timestamp,
            "difficulty": self.difficulty,
            "nonce": self.nonce
        }

    def to_bytes(self) -> bytes:
        return serialize(self.to_dict())

    def hash(self) -> str:
        return sha256_hex(self.to_bytes())