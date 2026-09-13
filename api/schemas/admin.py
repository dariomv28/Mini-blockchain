"""Strict schemas for admin operations (block templates and block submission)."""

from __future__ import annotations

from typing import Any
from pydantic import BaseModel, ConfigDict, Field, field_validator
from crypto.address import validate_address
from api.schemas.transaction import TxInputSubmitModel, TxOutputSubmitModel, _is_hex


class BlockTemplateRequest(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid")

    miner_address: str = Field(..., description="PYC address to receive block coinbase reward")
    max_transactions: int = Field(default=100, ge=0, le=100, description="Max pending transactions (0-100)")
    max_bytes: int = Field(default=100000, ge=0, le=100000, description="Max payload bytes (0-100000)")

    @field_validator("miner_address")
    @classmethod
    def validate_miner_addr(cls, v: str) -> str:
        if not validate_address(v):
            raise ValueError("miner_address is not a valid PYC address")
        return v


class BlockHeaderSubmitModel(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid")

    version: int = Field(default=1, description="Block version (must be 1)")
    previous_block_hash: str = Field(..., min_length=64, max_length=64, description="64-hex previous block hash")
    merkle_root: str = Field(..., min_length=64, max_length=64, description="64-hex declared Merkle root")
    timestamp: int = Field(..., ge=0, description="Block UNIX timestamp")
    difficulty: int = Field(..., ge=1, description="PoW target difficulty bits")
    nonce: int = Field(..., ge=0, description="Mining nonce")

    @field_validator("version")
    @classmethod
    def validate_version(cls, v: int) -> int:
        if v != 1:
            raise ValueError("Unsupported block version; must be 1")
        return v

    @field_validator("previous_block_hash", "merkle_root")
    @classmethod
    def validate_hex_fields(cls, v: str) -> str:
        if len(v) != 64 or not _is_hex(v):
            raise ValueError("Field must be a 64-character hexadecimal string")
        return v


class BlockTransactionSubmitModel(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid")

    version: int = Field(default=1, description="Transaction version")
    timestamp: int = Field(..., ge=0, description="Transaction creation timestamp")
    inputs: list[TxInputSubmitModel] = Field(default_factory=list, description="Inputs (empty for coinbase)")
    outputs: list[TxOutputSubmitModel] = Field(..., min_length=1, description="Outputs")

    @field_validator("version")
    @classmethod
    def validate_version(cls, v: int) -> int:
        if v != 1:
            raise ValueError("Unsupported transaction version; must be 1")
        return v


class BlockSubmitRequest(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid")

    header: BlockHeaderSubmitModel
    transactions: list[BlockTransactionSubmitModel] = Field(..., min_length=1, description="List of transactions including coinbase")


class BlockSubmitResponse(BaseModel):
    accepted: bool = Field(default=True)
    hash: str = Field(..., description="Computed hash of accepted block")
