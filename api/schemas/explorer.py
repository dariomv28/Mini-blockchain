"""Pydantic schemas for the PyChain Blockchain Explorer (Phase 14)."""

from __future__ import annotations

from typing import Any
from pydantic import BaseModel, Field


class ExplorerStatsResponse(BaseModel):
    height: int = Field(..., ge=0, description="Current blockchain tip height")
    tip_hash: str = Field(..., description="Current tip block hash (64 hex)")
    mempool_count: int = Field(..., ge=0, description="Number of pending transactions in mempool")
    peer_count: int = Field(..., ge=0, description="Number of connected network peers")
    total_confirmed_transactions: int = Field(..., ge=0, description="Total confirmed transactions in blockchain")


class ExplorerBlockListItem(BaseModel):
    height: int = Field(..., ge=0, description="Block height in the active chain")
    hash: str = Field(..., description="Block hash hex")
    previous_block_hash: str = Field(..., description="Preceding block hash hex")
    timestamp: int = Field(..., description="Block timestamp (epoch seconds)")
    transaction_count: int = Field(..., ge=0, description="Number of transactions in block")
    size_bytes: int = Field(..., ge=0, description="Canonical block size in bytes")
    miner_address: str | None = Field(default=None, description="Miner / coinbase recipient address")
    difficulty: int = Field(..., description="PoW target difficulty bits")
    nonce: int = Field(..., description="PoW mining nonce")


class ExplorerBlocksResponse(BaseModel):
    total_blocks: int = Field(..., ge=0, description="Total number of blocks in the chain")
    blocks: list[ExplorerBlockListItem] = Field(default_factory=list, description="Paginated list of blocks")
    limit: int = Field(..., ge=1, le=50, description="Requested page limit")
    offset: int = Field(..., ge=0, description="Requested offset")


class EnrichedTxInput(BaseModel):
    previous_tx_id: str = Field(..., description="Previous transaction hash hex")
    output_index: int = Field(..., ge=0, description="Output index within previous transaction")
    public_key: str = Field(..., description="Signer's public key hex")
    signature: str = Field(..., description="DER-encoded ECDSA signature hex")
    source_address: str | None = Field(default=None, description="Resolved source address (owner of spent UTXO)")
    amount: int | None = Field(default=None, description="Resolved input amount in PYC")


class EnrichedTxOutput(BaseModel):
    index: int = Field(..., ge=0, description="Output index within transaction")
    recipient_address: str = Field(..., description="Recipient address (PYC_...)")
    amount: int = Field(..., gt=0, description="Output amount in PYC")


class EnrichedTransactionResponse(BaseModel):
    txid: str = Field(..., description="64-character transaction ID hex")
    status: str = Field(..., description="'pending' or 'confirmed'")
    block_height: int | None = Field(default=None, description="Confirmed block height")
    block_hash: str | None = Field(default=None, description="Confirmed block hash hex")
    timestamp: int = Field(..., description="Creation timestamp")
    version: int = Field(default=1, description="Transaction version")
    is_coinbase: bool = Field(default=False, description="True if block reward / coinbase")
    inputs: list[EnrichedTxInput] = Field(default_factory=list, description="Resolved transaction inputs")
    outputs: list[EnrichedTxOutput] = Field(default_factory=list, description="Transaction outputs")
    fee: int = Field(default=0, ge=0, description="Transaction fee in PYC (0 for coinbase)")
    size_bytes: int = Field(default=0, ge=0, description="Transaction size in bytes")


class ExplorerBlockDetailResponse(BaseModel):
    height: int = Field(..., ge=0, description="Block height")
    hash: str = Field(..., description="Block hash hex")
    version: int = Field(default=1, description="Block version")
    previous_block_hash: str = Field(..., description="Preceding block hash hex")
    merkle_root: str = Field(..., description="Merkle root hash hex")
    timestamp: int = Field(..., description="Block timestamp (epoch seconds)")
    difficulty: int = Field(..., description="PoW difficulty bits")
    nonce: int = Field(..., description="Mining nonce")
    transaction_count: int = Field(..., ge=0, description="Number of transactions in block")
    size_bytes: int = Field(..., ge=0, description="Block size in bytes")
    miner_address: str | None = Field(default=None, description="Miner / coinbase recipient address")
    total_fees: int = Field(default=0, ge=0, description="Total transaction fees earned by miner")
    total_output_amount: int = Field(default=0, ge=0, description="Total value transacted in this block")
    transactions: list[EnrichedTransactionResponse] = Field(default_factory=list, description="List of enriched transactions")


class ExplorerAddressHistoryItem(BaseModel):
    txid: str = Field(..., description="Transaction hash hex")
    block_height: int | None = Field(default=None, description="Block height if confirmed, else None")
    timestamp: int = Field(..., description="Transaction timestamp")
    status: str = Field(..., description="'pending' or 'confirmed'")
    direction: str = Field(..., description="'sent', 'received', or 'mined'")
    amount: int = Field(..., ge=0, description="Amount transacted relative to address")
    fee: int = Field(default=0, ge=0, description="Transaction fee")


class ExplorerUTXOItem(BaseModel):
    txid: str = Field(..., description="Transaction ID of unspent output")
    output_index: int = Field(..., ge=0, description="Output index within transaction")
    amount: int = Field(..., gt=0, description="Amount in PYC")
    recipient_address: str = Field(..., description="Owner address")


class ExplorerAddressDetailResponse(BaseModel):
    address: str = Field(..., description="Target PYC address")
    confirmed_balance: int = Field(..., ge=0, description="Confirmed spendable balance")
    utxo_count: int = Field(..., ge=0, description="Number of confirmed unspent outputs")
    utxos: list[ExplorerUTXOItem] = Field(default_factory=list, description="List of unspent UTXOs")
    total_transactions: int = Field(..., ge=0, description="Total transactions involving address")
    transactions: list[ExplorerAddressHistoryItem] = Field(default_factory=list, description="Paginated transaction history")
    limit: int = Field(..., ge=1, le=100, description="Page limit")
    offset: int = Field(..., ge=0, description="Page offset")


class ExplorerMempoolEntryItem(BaseModel):
    txid: str = Field(..., description="Transaction hash hex")
    timestamp: int = Field(..., description="Transaction timestamp")
    inputs_count: int = Field(..., ge=0, description="Number of inputs")
    outputs_count: int = Field(..., ge=0, description="Number of outputs")
    fee: int = Field(..., ge=0, description="Transaction fee in PYC")
    size_bytes: int = Field(..., ge=0, description="Transaction size in bytes")
    status: str = Field(default="pending", description="Status string")


class ExplorerMempoolResponse(BaseModel):
    count: int = Field(..., ge=0, description="Total pending transactions in mempool")
    total_bytes: int = Field(..., ge=0, description="Total size in bytes of mempool")
    transactions: list[ExplorerMempoolEntryItem] = Field(default_factory=list, description="Pending transaction entries")


class ExplorerSearchResponse(BaseModel):
    query: str = Field(..., description="Queried string")
    result_type: str = Field(..., description="'block', 'transaction', 'address', or 'not_found'")
    target_url: str | None = Field(default=None, description="Suggested redirect path, e.g. /explorer/block/10")
    payload: dict[str, Any] | None = Field(default=None, description="Summary info of resolved target")
