"""Admin operations endpoint (development/demo only)."""

from __future__ import annotations

from fastapi import APIRouter, Depends, status
from network.node import Node
from api.dependencies import get_node, verify_admin_token
from api.errors import APIError
from api.schemas.admin import (
    BlockSubmitRequest,
    BlockSubmitResponse,
    BlockTemplateRequest,
)
from api.services.serializers import request_to_block

router = APIRouter(prefix="/admin", tags=["Admin"], dependencies=[Depends(verify_admin_token)])


@router.post("/validate-chain")
async def validate_chain(node: Node = Depends(get_node)) -> dict[str, bool]:
    is_valid = await node.validate_chain()
    return {"valid": bool(is_valid)}


@router.post("/blocks/template")
async def create_block_template(
    body: BlockTemplateRequest,
    node: Node = Depends(get_node),
) -> dict:
    template = await node.create_mempool_block_template(
        body.miner_address,
        max_transactions=body.max_transactions,
        max_bytes=body.max_bytes,
    )
    return {
        "header": template.header().to_dict(),
        "transactions": [tx.to_dict() for tx in template.transactions],
    }


@router.post("/blocks", response_model=BlockSubmitResponse, status_code=status.HTTP_201_CREATED)
async def submit_block(
    body: BlockSubmitRequest,
    node: Node = Depends(get_node),
) -> dict:
    block = request_to_block(body)
    accepted = await node.accept_block(block)
    if not accepted:
        raise APIError(
            status.HTTP_422_UNPROCESSABLE_CONTENT,
            "BLOCK_REJECTED",
            "Block was rejected by node consensus or validation rules",
        )
    return {
        "accepted": True,
        "hash": block.hash(),
    }
