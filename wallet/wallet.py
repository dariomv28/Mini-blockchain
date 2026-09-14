from dataclasses import dataclass


@dataclass(frozen=True)
class Wallet:
    address: str
    public_key: str
    encrypted_private_key: bytes
    key_version: int = 1
