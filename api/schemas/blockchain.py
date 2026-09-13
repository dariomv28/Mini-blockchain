"""Schemas for blockchain entities (Block, Transaction, UTXO)."""

from __future__ import annotations

from pydantic import BaseModel, Field


class TxInputModel(BaseModel):
    previous_tx_id: str = Field(..., description="Previous transaction hash hex")
    output_index: int = Field(..., ge=0, description="Output index within previous transaction")
    public_key: str = Field(..., description="Signer's public key hex")
    signature: str = Field(..., description="DER-encoded ECDSA signature hex")


class TxOutputModel(BaseModel):
    amount: int = Field(..., gt=0, description="Amount of PYC transferred")
    recipient_address: str = Field(..., description="Recipient address (PYC_...)")


class TransactionResponse(BaseModel):
    txid: str = Field(..., description="Transaction hash identifier")
    version: int = Field(default=1, description="Transaction version")
    timestamp: int = Field(..., description="Transaction creation timestamp")
    inputs: list[TxInputModel] = Field(default_factory=list, description="List of transaction inputs")
    outputs: list[TxOutputModel] = Field(..., description="List of transaction outputs")
    is_coinbase: bool = Field(default=False, description="True if this is a block coinbase reward")


class BlockHeaderModel(BaseModel):
    version: int = Field(default=1, description="Block version")
    previous_block_hash: str = Field(..., description="Hash of the preceding block")
    merkle_root: str = Field(..., description="Merkle root of block transactions")
    timestamp: int = Field(..., description="Block timestamp")
    difficulty: int = Field(..., description="PoW target difficulty bits")
    nonce: int = Field(..., description="Mining nonce")


class BlockResponse(BaseModel):
    height: int | None = Field(default=None, description="Block height in the active chain")
    hash: str = Field(..., description="Block hash hex")
    header: BlockHeaderModel = Field(..., description="Block header")
    transaction_count: int = Field(..., description="Number of transactions in block")
    transactions: list[TransactionResponse] = Field(default_factory=list, description="Transactions included in block")


class UTXOResponse(BaseModel):
    txid: str = Field(..., description="Transaction ID")
    output_index: int = Field(..., ge=0, description="Output index")
    amount: int = Field(..., gt=0, description="Output amount in PYC")
    recipient_address: str = Field(..., description="Owner address (PYC_...)")


class BalanceResponse(BaseModel):
    address: str = Field(..., description="Queried address")
    confirmed_balance: int = Field(..., ge=0, description="Total confirmed spendable balance")
    utxo_count: int = Field(..., ge=0, description="Number of confirmed UTXOs")


class TransactionDetailResponse(BaseModel):
    transaction: TransactionResponse
    status: str = Field(..., description="'pending' or 'confirmed'")
    height: int | None = Field(default=None, description="Block height if confirmed")
    block_hash: str | None = Field(default=None, description="Block hash if confirmed")


class MempoolResponse(BaseModel):
    count: int = Field(..., ge=0, description="Number of pending transactions")
    total_bytes: int = Field(..., ge=0, description="Total canonical bytes in mempool")
    transactions: list[TransactionResponse] = Field(default_factory=list, description="Pending transactions")
