"""Pydantic schemas for mining candidate templates and background jobs."""

from __future__ import annotations

from typing import Any
from pydantic import BaseModel, Field


class CandidateTemplateRequest(BaseModel):
    max_transactions: int = Field(default=100, ge=0, le=1000)
    max_bytes: int = Field(default=100_000, ge=1000, le=1_000_000)


class CandidateTemplateResponse(BaseModel):
    previous_block_hash: str
    merkle_root: str
    difficulty: int
    nonce: int = 0
    template_height: int
    timestamp: int
    miner_address: str
    transactions: list[dict[str, Any]]
    transaction_count: int
    subsidy: int = 50
    fees: int = 0
    total_reward: int = 50


class MiningJobStartRequest(BaseModel):
    max_transactions: int = Field(default=100, ge=0, le=1000)
    max_bytes: int = Field(default=100_000, ge=1000, le=1_000_000)
    max_nonce: int = Field(default=500_000, ge=1, le=10_000_000)


class MiningJobStartResponse(BaseModel):
    job_id: str
    status: str = "QUEUED"


class MiningJobResponse(BaseModel):
    id: str
    status: str
    miner_address: str
    created_at: float
    started_at: float | None = None
    finished_at: float | None = None
    template_height: int
    previous_hash: str
    transaction_count: int
    difficulty: int
    result_hash: str | None = None
    nonce: int | None = None
    hashes_tried: int = 0
    current_hash: str | None = None
    elapsed_seconds: float = 0.0
    accepted: bool | None = None
    error: str | None = None
    subsidy: int = 50
    fees: int = 0
    total_reward: int = 50


class MiningCancelResponse(BaseModel):
    job_id: str
    cancelled: bool
