"""Node operational status endpoint."""

from __future__ import annotations

from fastapi import APIRouter, Depends
from network.node import Node
from api.dependencies import get_node
from api.schemas.node import NodeStatusResponse

router = APIRouter(prefix="/node", tags=["Node"])


@router.get("/status", response_model=NodeStatusResponse)
async def get_node_status(node: Node = Depends(get_node)) -> dict:
    status_data = await node.get_status()
    status_data["node_id"] = node.node_id
    status_data["endpoint"] = list(node.endpoint) if node.endpoint else None
    return status_data

