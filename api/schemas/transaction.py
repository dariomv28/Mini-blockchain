"""Strict request schemas for submitting transactions."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field, field_validator
from crypto.address import validate_address


def _is_hex(value: str) -> bool:
    return bool(value) and all(c in "0123456789abcdefABCDEF" for c in value)


class TxInputSubmitModel(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid")

    previous_tx_id: str = Field(..., description="64-hex previous transaction ID")
    output_index: int = Field(..., ge=0, description="Previous output index")
    public_key: str = Field(..., description="Signer public key hex")
    signature: str = Field(..., description="DER signature hex")

    @field_validator("previous_tx_id")
    @classmethod
    def validate_txid(cls, v: str) -> str:
        if len(v) != 64 or not _is_hex(v):
            raise ValueError("previous_tx_id must be a 64-character hexadecimal string")
        return v

    @field_validator("public_key")
    @classmethod
    def validate_pubkey(cls, v: str) -> str:
        if not _is_hex(v):
            raise ValueError("public_key must be a hexadecimal string")
        return v

    @field_validator("signature")
    @classmethod
    def validate_sig(cls, v: str) -> str:
        if not _is_hex(v):
            raise ValueError("signature must be a hexadecimal string")
        return v


class TxOutputSubmitModel(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid")

    amount: int = Field(..., gt=0, description="Transferred amount in PYC")
    recipient_address: str = Field(..., description="Recipient PYC address")

    @field_validator("recipient_address")
    @classmethod
    def validate_addr(cls, v: str) -> str:
        if not validate_address(v):
            raise ValueError("recipient_address is not a valid PYC address")
        return v


class TransactionSubmitRequest(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid")

    version: int = Field(default=1, description="Transaction version (must be 1)")
    timestamp: int = Field(..., ge=0, description="Creation timestamp")
    inputs: list[TxInputSubmitModel] = Field(..., min_length=1, description="Transaction inputs")
    outputs: list[TxOutputSubmitModel] = Field(..., min_length=1, description="Transaction outputs")

    @field_validator("version")
    @classmethod
    def validate_version(cls, v: int) -> int:
        if v != 1:
            raise ValueError("Unsupported transaction version; must be 1")
        return v


class TransactionSubmitResponse(BaseModel):
    txid: str = Field(..., description="Transaction hash identifier")
    status: str = Field(default="pending", description="Admission status")
    accepted: bool = Field(default=True, description="Whether node accepted transaction")
