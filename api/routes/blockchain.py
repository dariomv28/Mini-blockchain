"""Routes for blocks, transactions, addresses, and balances."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Path, Query, status
from crypto.address import validate_address
from network.node import Node
from api.dependencies import get_node
from api.errors import APIError
from api.schemas.blockchain import (
    BalanceResponse,
    BlockResponse,
    TransactionDetailResponse,
    UTXOResponse,
)
from api.schemas.transaction import (
    TransactionSubmitRequest,
    TransactionSubmitResponse,
)
from api.services.serializers import (
    block_to_response,
    request_to_transaction,
    transaction_to_response,
    utxo_to_response,
)

router = APIRouter(tags=["Blockchain"])


def _validate_hex64(value: str, name: str) -> str:
    if not isinstance(value, str) or len(value) != 64 or not all(c in "0123456789abcdefABCDEF" for c in value):
        raise APIError(status.HTTP_400_BAD_REQUEST, "INVALID_HASH", f"{name} must be a 64-character hexadecimal string")
    return value.lower()


def _validate_pyc_address(address: str) -> str:
    if not validate_address(address):
        raise APIError(status.HTTP_400_BAD_REQUEST, "INVALID_ADDRESS", f"'{address}' is not a valid PYC address")
    return address


# ---------------------------------------------------------------------------
# Block Endpoints
# ---------------------------------------------------------------------------

@router.get("/blocks/latest", response_model=BlockResponse)
async def get_latest_block(node: Node = Depends(get_node)) -> dict:
    info = await node.get_latest_block_info()
    if info is None:
        raise APIError(status.HTTP_404_NOT_FOUND, "BLOCK_NOT_FOUND", "No blocks exist in the blockchain")
    return block_to_response(info["block"], height=info["height"])


@router.get("/blocks/hash/{block_hash}", response_model=BlockResponse)
async def get_block_by_hash(
    block_hash: str = Path(..., description="64-character hex block hash"),
    node: Node = Depends(get_node),
) -> dict:
    valid_hash = _validate_hex64(block_hash, "block_hash")
    info = await node.get_block_info_by_hash(valid_hash)
    if info is None:
        raise APIError(status.HTTP_404_NOT_FOUND, "BLOCK_NOT_FOUND", f"Block with hash '{valid_hash}' was not found")
    return block_to_response(info["block"], height=info["height"])


@router.get("/blocks/{height}", response_model=BlockResponse)
async def get_block_by_height(
    height: int = Path(..., ge=0, description="Block height (>= 0)"),
    node: Node = Depends(get_node),
) -> dict:
    latest_info = await node.get_latest_block_info()
    current_height = latest_info["height"] if latest_info else 0
    if height > current_height:
        raise APIError(status.HTTP_404_NOT_FOUND, "BLOCK_NOT_FOUND", f"Block at height {height} does not exist (current height: {current_height})")

    block = await node.get_block_by_height(height)
    if block is None:
        raise APIError(status.HTTP_404_NOT_FOUND, "BLOCK_NOT_FOUND", f"Block at height {height} was not found")

    return block_to_response(block, height=height)


@router.get("/blocks", response_model=list[BlockResponse])
async def get_blocks(
    start: int = Query(default=0, ge=0, description="Starting block height"),
    limit: int = Query(default=20, ge=1, le=100, description="Number of blocks (1-100)"),
    node: Node = Depends(get_node),
) -> list[dict]:
    if start < 0 or limit < 1 or limit > 100:
        raise APIError(status.HTTP_400_BAD_REQUEST, "INVALID_PAGINATION", "limit must be between 1 and 100, start >= 0")
    blocks = await node.get_blocks(start, limit)
    return [block_to_response(block, height=start + i) for i, block in enumerate(blocks)]


# ---------------------------------------------------------------------------
# Address & Balance Endpoints
# ---------------------------------------------------------------------------

@router.get("/addresses/{address}/balance", response_model=BalanceResponse)
async def get_address_balance(
    address: str = Path(..., description="Target PYC address"),
    node: Node = Depends(get_node),
) -> dict:
    valid_address = _validate_pyc_address(address)
    info = await node.get_address_info(valid_address)
    return {
        "address": valid_address,
        "confirmed_balance": info["confirmed_balance"],
        "utxo_count": info["utxo_count"],
    }


@router.get("/addresses/{address}/utxos", response_model=list[UTXOResponse])
async def get_address_utxos(
    address: str = Path(..., description="Target PYC address"),
    node: Node = Depends(get_node),
) -> list[dict]:
    valid_address = _validate_pyc_address(address)
    info = await node.get_address_info(valid_address)
    return [utxo_to_response(outpoint, output) for outpoint, output in info["utxos"].items()]



# ---------------------------------------------------------------------------
# Transaction Endpoints
# ---------------------------------------------------------------------------

@router.get("/transactions/{txid}", response_model=TransactionDetailResponse)
async def get_transaction(
    txid: str = Path(..., description="64-character transaction ID"),
    node: Node = Depends(get_node),
) -> dict:
    valid_txid = _validate_hex64(txid, "txid")
    match = await node.find_transaction(valid_txid)
    if match is None:
        raise APIError(status.HTTP_404_NOT_FOUND, "TRANSACTION_NOT_FOUND", f"Transaction '{valid_txid}' was not found in mempool or confirmed blocks")

    return {
        "transaction": transaction_to_response(match["transaction"]),
        "status": match["status"],
        "height": match["height"],
        "block_hash": match["block_hash"],
    }


@router.post("/transactions", response_model=TransactionSubmitResponse, status_code=status.HTTP_201_CREATED)
async def submit_transaction(
    body: TransactionSubmitRequest,
    node: Node = Depends(get_node),
) -> dict:
    try:
        tx = request_to_transaction(body)
    except Exception as error:
        raise APIError(status.HTTP_400_BAD_REQUEST, "MALFORMED_TRANSACTION", f"Could not parse transaction: {error}")

    accepted = await node.submit_transaction(tx)
    if not accepted:
        raise APIError(status.HTTP_422_UNPROCESSABLE_CONTENT, "TRANSACTION_REJECTED", "Transaction was rejected by node admission rules (e.g. invalid signature, double spend, or fee)")


    return {
        "txid": tx.txid(),
        "status": "pending",
        "accepted": True,
    }
