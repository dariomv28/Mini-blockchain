"""Routes for PyChain Blockchain Explorer (Phase 14)."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Path, Query
from auth.dependencies import get_current_user
from network.node import Node
from api.dependencies import get_node
from api.services.explorer_service import explorer_service
from api.schemas.explorer import (
    EnrichedTransactionResponse,
    ExplorerAddressDetailResponse,
    ExplorerBlockDetailResponse,
    ExplorerBlocksResponse,
    ExplorerMempoolResponse,
    ExplorerSearchResponse,
    ExplorerStatsResponse,
)

# Explorer router: Enforces authentication on all endpoints as requested
router = APIRouter(
    prefix="/explorer",
    tags=["Explorer"],
    dependencies=[Depends(get_current_user)],
)


@router.get("/stats", response_model=ExplorerStatsResponse)
async def get_explorer_stats(node: Node = Depends(get_node)) -> ExplorerStatsResponse:
    return await explorer_service.get_stats(node)


@router.get("/blocks", response_model=ExplorerBlocksResponse)
async def get_explorer_blocks(
    limit: int = Query(default=10, ge=1, le=50, description="Max blocks to return (1-50)"),
    offset: int = Query(default=0, ge=0, description="Pagination offset"),
    node: Node = Depends(get_node),
) -> ExplorerBlocksResponse:
    return await explorer_service.get_latest_blocks(node, limit=limit, offset=offset)


@router.get("/blocks/height/{height}", response_model=ExplorerBlockDetailResponse)
async def get_explorer_block_by_height(
    height: int = Path(..., ge=0, description="Block height"),
    node: Node = Depends(get_node),
) -> ExplorerBlockDetailResponse:
    return await explorer_service.get_block_by_height(node, height=height)


@router.get("/blocks/hash/{block_hash}", response_model=ExplorerBlockDetailResponse)
async def get_explorer_block_by_hash(
    block_hash: str = Path(..., description="64-character hexadecimal block hash"),
    node: Node = Depends(get_node),
) -> ExplorerBlockDetailResponse:
    return await explorer_service.get_block_by_hash(node, block_hash=block_hash)


@router.get("/transactions/{txid}", response_model=EnrichedTransactionResponse)
async def get_explorer_transaction(
    txid: str = Path(..., description="64-character transaction ID"),
    node: Node = Depends(get_node),
) -> EnrichedTransactionResponse:
    return await explorer_service.get_transaction(node, txid=txid)


@router.get("/addresses/{address}", response_model=ExplorerAddressDetailResponse)
async def get_explorer_address(
    address: str = Path(..., description="Target PYC address"),
    limit: int = Query(default=20, ge=1, le=100, description="Max history records (1-100)"),
    offset: int = Query(default=0, ge=0, description="History pagination offset"),
    node: Node = Depends(get_node),
) -> ExplorerAddressDetailResponse:
    return await explorer_service.get_address_detail(node, address=address, limit=limit, offset=offset)


@router.get("/mempool", response_model=ExplorerMempoolResponse)
async def get_explorer_mempool(node: Node = Depends(get_node)) -> ExplorerMempoolResponse:
    return await explorer_service.get_mempool(node)


@router.get("/search", response_model=ExplorerSearchResponse)
async def search_explorer(
    q: str = Query(..., min_length=1, max_length=100, description="Search term (height, hash, txid, or address)"),
    node: Node = Depends(get_node),
) -> ExplorerSearchResponse:
    return await explorer_service.search(node, query=q)
