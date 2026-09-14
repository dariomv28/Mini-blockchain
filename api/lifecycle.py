"""FastAPI lifespan context manager controlling the embedded Node lifecycle."""

from __future__ import annotations

import logging
import asyncio
import secrets
from pathlib import Path
from contextlib import asynccontextmanager
from fastapi import FastAPI
from network.config import NodeConfig
from network.node import Node
from api.config import ApiConfig
from api.websocket.manager import WebSocketManager
from appdb.database import AppDatabase
from auth.password import hash_password
from auth.service import AuthService
from auth.token import TokenService
from wallet.keystore import KeyStore
from wallet.service import WalletService
from api.services.mining_service import MiningService

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

    # Validate secrets before creating/opening databases or binding sockets.
    master = config.wallet_master_key.get_secret_value() if config.wallet_master_key else ""
    jwt_secret = config.jwt_secret.get_secret_value() if config.jwt_secret else ""
    if not master or master == "CHANGE_ME":
        raise RuntimeError("PYC_WALLET_MASTER_KEY must be configured")
    if not jwt_secret or jwt_secret == "CHANGE_ME" or len(jwt_secret.encode("utf-8")) < 32:
        raise RuntimeError("PYC_JWT_SECRET must contain at least 32 bytes of secret material")
    if not config.demo_mode and not config.cookie_secure:
        raise RuntimeError("PYC_COOKIE_SECURE must be enabled outside demo mode")
    if config.node_db and config.app_db != ":memory:" and Path(config.app_db).resolve() == Path(config.node_db).resolve():
        raise RuntimeError("Application and blockchain databases must be separate")
    keystore = KeyStore(master)
    database = AppDatabase(config.app_db)
    node = None
    ws_manager: WebSocketManager | None = None
    wallet_service = None
    mining_service = None
    try:
        keystore.validate_database(database)
        dummy_hash = await asyncio.to_thread(hash_password, secrets.token_urlsafe(32))
        app.state.app_database = database
        app.state.tokens = TokenService(jwt_secret, config.session_seconds)
        app.state.auth_service = AuthService(database, keystore, dummy_hash)
        logger.info("Starting PyChain Node (port=%d, db=%s)...", config.node_port, config.node_db_path)
        node = Node(node_config)
        await node.start()
        app.state.node = node
        wallet_service = WalletService(database, node, keystore)
        app.state.wallet_service = wallet_service
        ws_manager = WebSocketManager(config)
        await ws_manager.start(node)
        app.state.ws_manager = ws_manager
        mining_service = MiningService(node, ws_manager, config)
        app.state.mining_service = mining_service
        logger.info("PyChain Node, WebSocket manager, and Mining service started successfully.")
        yield
    finally:
        logger.info("Shutting down PyChain API and embedded node...")
        if mining_service is not None:
            try:
                await mining_service.close()
            except Exception as exc:
                logger.error("Error stopping MiningService: %s", exc)
        if wallet_service is not None:
            await wallet_service.close()
        if ws_manager is not None:
            try:
                await ws_manager.stop()
            except Exception as exc:
                logger.error("Error stopping WebSocketManager: %s", exc)
        if node is not None:
            try:
                await node.stop()
            except Exception as exc:
                logger.error("Error stopping Node: %s", exc)
        database.close()
        logger.info("PyChain Node shut down cleanly.")
