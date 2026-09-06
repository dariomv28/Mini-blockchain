import time
from dataclasses import dataclass, field

from blockchain.block_header import BlockHeader
from blockchain.merkle import calculate_merkle_root
from transaction.transaction import Transaction

@dataclass
class Block:
    transactions: list[Transaction]
    previous_block_hash: str

    timestamp: int = field(
        default_factory=lambda: int(
            time.time()
        )
    )

    version: int = 1
    difficulty: int = 1
    nonce: int = 0

    merkle_root: str = field(
        init=False
    )

    def __post_init__(self) -> None:
        self.refresh_merkle_root()

    def refresh_merkle_root(
        self,
    ) -> None:
        self.merkle_root = (
            calculate_merkle_root(
                self.transactions
            )
        )

    def header(self) -> BlockHeader:
        return BlockHeader(
            version=self.version,
            previous_block_hash=(
                self.previous_block_hash
            ),
            merkle_root=self.merkle_root,
            timestamp=self.timestamp,
            difficulty=self.difficulty,
            nonce=self.nonce,
        )

    def hash(self) -> str:
        return self.header().hash()

    def to_dict(self) -> dict:
        return {
            "header": self.header().to_dict(),
            "transactions": [
                transaction.to_dict()
                for transaction
                in self.transactions
            ],
        }