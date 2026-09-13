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
    transactions = await node.get_pending_transactions()
    total_bytes = sum(len(serialize(tx.to_dict())) for tx in transactions)
    return {
        "count": len(transactions),
        "total_bytes": total_bytes,
        "transactions": [transaction_to_response(tx) for tx in transactions],
    }
