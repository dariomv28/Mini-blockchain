"""Schemas for Node and Health endpoints."""

from __future__ import annotations

from typing import Any
from pydantic import BaseModel, Field


class HealthResponse(BaseModel):
    status: str = Field(default="ok", description="API health status")
    node_state: str = Field(..., description="Lifecycle state of the embedded blockchain node")


class NodeStatusResponse(BaseModel):
    node_id: str = Field(..., description="Unique identifier of this node instance")
    endpoint: list[Any] | None = Field(default=None, description="Host and port the node server listens on")
    state: str = Field(..., description="Node state: RUNNING, STOPPED, etc.")
    height: int = Field(..., description="Current tip height of the local chain")
    tip_hash: str = Field(..., description="Hash of the current tip block")
    pending_count: int = Field(..., description="Number of unconfirmed transactions in mempool")
    peers: list[dict[str, Any]] = Field(default_factory=list, description="Connected peer information")
    counters: dict[str, int] = Field(default_factory=dict, description="Operational event counters")
    inbound_events: int = Field(..., description="Current inbound event queue reservations")
    inbound_bytes: int = Field(..., description="Current inbound byte reservations")
