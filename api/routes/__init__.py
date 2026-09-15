"""Router grouping for API v1."""

from __future__ import annotations

from fastapi import APIRouter, Depends, WebSocket
from network.node import Node
from api.config import ApiConfig
from api.dependencies import get_config, get_node
from api.routes.admin import router as admin_router
from api.routes.blockchain import router as blockchain_router
from api.routes.explorer import router as explorer_router
from api.routes.health import router as health_router
from api.routes.mempool import router as mempool_router
from api.routes.node import router as node_router

api_v1_router = APIRouter(prefix="/api/v1")

# Mount sub-routers
api_v1_router.include_router(health_router)
api_v1_router.include_router(node_router)
api_v1_router.include_router(blockchain_router)
api_v1_router.include_router(mempool_router)
api_v1_router.include_router(explorer_router)


@api_v1_router.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    # Access node and ws_manager stored on app.state
    node: Node = websocket.app.state.node
    ws_manager = websocket.app.state.ws_manager
    await ws_manager.handle_connection(websocket, node)
