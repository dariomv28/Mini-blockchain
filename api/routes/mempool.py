"""Mempool query endpoint."""

from __future__ import annotations

from fastapi import APIRouter, Depends
from crypto.hash import serialize
from network.node import Node
from api.dependencies import get_node
from api.schemas.blockchain import MempoolResponse
from api.services.serializers import transaction_to_response

router = APIRouter(prefix="/mempool", tags=["Mempool"])


@router.get("", response_model=MempoolResponse)
async def get_mempool(node: Node = Depends(get_node)) -> dict:
    entries = await node.get_pending_entries()
    total_bytes = sum(entry["size_bytes"] for entry in entries)
    return {
        "count": len(entries),
        "total_bytes": total_bytes,
        "transactions": [
            transaction_to_response(entry["transaction"], fee=entry["fee"])
            for entry in entries
        ],
    }
