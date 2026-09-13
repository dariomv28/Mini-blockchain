"""FastAPI lifespan context manager controlling the embedded Node lifecycle."""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from fastapi import FastAPI
from network.config import NodeConfig
from network.node import Node
from api.config import ApiConfig
from api.websocket.manager import WebSocketManager

logger = logging.getLogger("pychain.api.lifecycle")


def _parse_seeds(seeds: list[str]) -> tuple[tuple[str, int], ...]:
    parsed: list[tuple[str, int]] = []
    for s in seeds:
        if ":" in s:
            host, port_str = s.rsplit(":", 1)
            parsed.append((host.strip(), int(port_str.strip())))
    return tuple(parsed)


@asynccontextmanager
async def lifespan(app: FastAPI):
    config: ApiConfig = getattr(app.state, "config", None)
    if config is None:
        config = ApiConfig()
        app.state.config = config

    # Initialize NodeConfig
    node_config = NodeConfig(
        host=config.node_host,
        port=config.node_port,
        db_path=config.node_db_path,
        seeds=_parse_seeds(config.node_seeds),
    )

    logger.info("Starting PyChain Node (port=%d, db=%s)...", config.node_port, config.node_db_path)
    node = Node(node_config)
    await node.start()
    app.state.node = node

    ws_manager: WebSocketManager | None = None
    try:
        ws_manager = WebSocketManager(config)
        await ws_manager.start(node)
        app.state.ws_manager = ws_manager
        logger.info("PyChain Node and WebSocket manager started successfully.")
        yield
    finally:
        logger.info("Shutting down PyChain API and embedded node...")
        if ws_manager is not None:
            try:
                await ws_manager.stop()
            except Exception as exc:
                logger.error("Error stopping WebSocketManager: %s", exc)
        try:
            await node.stop()
        except Exception as exc:
            logger.error("Error stopping Node: %s", exc)
        logger.info("PyChain Node shut down cleanly.")
