"""Health check endpoint."""

from __future__ import annotations

from fastapi import APIRouter, Depends
from network.node import Node
from api.dependencies import get_node
from api.schemas.node import HealthResponse

router = APIRouter(tags=["Health"])


@router.get("/health", response_model=HealthResponse)
async def get_health(node: Node = Depends(get_node)) -> HealthResponse:
    return HealthResponse(
        status="ok",
        node_state=node.state,
    )
