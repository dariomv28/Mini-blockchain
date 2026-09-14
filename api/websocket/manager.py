"""WebSocket manager with per-client outgoing queues, idle heartbeat timeouts, and isolated writers."""

from __future__ import annotations

import asyncio
import logging
import time
from collections import defaultdict
from dataclasses import dataclass
from typing import Any
from fastapi import WebSocket, status
from network.node import Node
from api.config import ApiConfig

logger = logging.getLogger("pychain.api.websocket")


@dataclass
class ClientSession:
    websocket: WebSocket
    ip: str
    queue: asyncio.Queue[dict[str, Any] | str]
    writer_task: asyncio.Task
    done_event: asyncio.Event
    close_code: int = status.WS_1000_NORMAL_CLOSURE


class WebSocketManager:
    def __init__(self, config: ApiConfig):
        self.config = config
        self._clients: dict[WebSocket, ClientSession] = {}
        self._ip_counts: dict[str, int] = defaultdict(int)
        self._total_reserved = 0
        self._broadcast_task: asyncio.Task | None = None
        self._running = False
        self._lock = asyncio.Lock()
        self._stop_lock = asyncio.Lock()
        # Handlers own reservations from before accept until their final cleanup.
        self._handlers: dict[WebSocket, asyncio.Task] = {}

    @property
    def total_clients(self) -> int:
        return len(self._clients)

    def _get_client_ip(self, websocket: WebSocket) -> str:
        client = websocket.client
        return client.host if client is not None and client.host else "127.0.0.1"

    def is_origin_allowed(self, origin: str | None) -> bool:
        if not origin:
            # Native or testing non-browser clients omitting Origin are allowed
            return True
        allowed = {self.config.frontend_origin.rstrip("/")}
        for item in list(allowed):
            if "localhost" in item:
                allowed.add(item.replace("localhost", "127.0.0.1"))
            elif "127.0.0.1" in item:
                allowed.add(item.replace("127.0.0.1", "localhost"))
        return origin.rstrip("/") in allowed

    async def start(self, node: Node) -> None:
        self._running = True
        self._broadcast_task = asyncio.create_task(
            self._status_broadcast_loop(node),
            name="ws-status-broadcast",
        )

    async def stop(self) -> None:
        async with self._stop_lock:
            await self._stop()

    async def _stop(self) -> None:
        self._running = False
        if self._broadcast_task and not self._broadcast_task.done():
            self._broadcast_task.cancel()
            try:
                await self._broadcast_task
            except asyncio.CancelledError:
                pass

        # Cancel and await owners, including handshakes and initial status reads.
        # Only their finally blocks release reservations; never reset counters.
        async with self._lock:
            handlers = list(self._handlers.values())
        for handler in handlers:
            handler.cancel()
        await asyncio.gather(*handlers, return_exceptions=True)

    async def _close(self, websocket: WebSocket, code: int) -> None:
        try:
            await asyncio.wait_for(websocket.close(code=code), timeout=2.0)
        except Exception:
            pass

    async def _client_writer(self, websocket: WebSocket, queue: asyncio.Queue, done_event: asyncio.Event) -> None:
        try:
            while not done_event.is_set():
                try:
                    msg = await asyncio.wait_for(queue.get(), timeout=1.0)
                except asyncio.TimeoutError:
                    continue

                try:
                    send = websocket.send_text(msg) if isinstance(msg, str) else websocket.send_json(msg)
                    await asyncio.wait_for(send, timeout=2.0)
                except Exception as exc:
                    logger.debug("Writer failed sending to client: %s", exc)
                    session = self._clients.get(websocket)
                    if session is not None:
                        session.close_code = status.WS_1013_TRY_AGAIN_LATER
                    done_event.set()
                    break
                finally:
                    queue.task_done()
        except asyncio.CancelledError:
            pass

    async def _receive(self, websocket: WebSocket, done_event: asyncio.Event) -> dict:
        # Wake the reader immediately when its writer fails or its queue fills.
        receive_task = asyncio.create_task(websocket.receive())
        done_task = asyncio.create_task(done_event.wait())
        try:
            completed, _ = await asyncio.wait(
                (receive_task, done_task), timeout=1.0,
                return_when=asyncio.FIRST_COMPLETED,
            )
            if done_task in completed:
                return {"type": "websocket.disconnect"}
            if receive_task in completed:
                return receive_task.result()
            raise asyncio.TimeoutError
        finally:
            receive_task.cancel()
            done_task.cancel()
            await asyncio.gather(receive_task, done_task, return_exceptions=True)

    async def handle_connection(self, websocket: WebSocket, node: Node) -> None:
        # 1. Validate Origin header
        origin = websocket.headers.get("origin")
        if not self.is_origin_allowed(origin):
            logger.warning("Rejected WebSocket connection: unauthorized origin %r", origin)
            await self._close(websocket, status.WS_1008_POLICY_VIOLATION)
            return

        ip = self._get_client_ip(websocket)

        # 2. Reserve connection slot before handshake
        async with self._lock:
            reject_code = None
            if not self._running or self._total_reserved >= self.config.ws_max_clients:
                reject_code = status.WS_1013_TRY_AGAIN_LATER
            elif self._ip_counts.get(ip, 0) >= self.config.ws_max_clients_per_ip:
                reject_code = status.WS_1008_POLICY_VIOLATION
            else:
                self._total_reserved += 1
                self._ip_counts[ip] += 1
                self._handlers[websocket] = asyncio.current_task()
        if reject_code is not None:
            # No transport await is allowed while holding the admission lock.
            await self._close(websocket, reject_code)
            return

        session = None
        try:
            await asyncio.wait_for(websocket.accept(), timeout=2.0)
            status_data = await node.get_status()
            initial_msg = {
                "type": "node_status",
                "payload": {
                    "height": status_data["height"],
                    "tip_hash": status_data["tip_hash"],
                    "pending_count": status_data["pending_count"],
                    "state": status_data["state"],
                    "peer_count": len(status_data["peers"]),
                },
            }
            queue: asyncio.Queue = asyncio.Queue(maxsize=2)
            queue.put_nowait(initial_msg)
            done_event = asyncio.Event()
            writer_task = asyncio.create_task(
                self._client_writer(websocket, queue, done_event), name=f"ws-writer-{ip}",
            )
            session = ClientSession(websocket, ip, queue, writer_task, done_event)
            self._clients[websocket] = session

            # All outgoing messages use one writer, including initial status/pong.
            last_client_activity = time.monotonic()
            while self._running and not done_event.is_set():
                try:
                    raw_msg = await self._receive(websocket, done_event)
                except asyncio.TimeoutError:
                    # Check idle timeout (60 seconds) without reset by outgoing status
                    if time.monotonic() - last_client_activity >= self.config.ws_idle_timeout:
                        logger.debug("Closing WebSocket client %s: idle timeout exceeded", ip)
                        session.close_code = status.WS_1008_POLICY_VIOLATION
                        break
                    continue

                if raw_msg["type"] == "websocket.disconnect":
                    break

                if raw_msg["type"] == "websocket.receive":
                    # Check for unsupported binary frame
                    if raw_msg.get("bytes") is not None:
                        logger.debug("Closing WebSocket client %s: binary frames unsupported", ip)
                        session.close_code = status.WS_1003_UNSUPPORTED_DATA
                        break

                    text = raw_msg.get("text", "")
                    # Check inbound frame byte limit (4 KiB)
                    if len(text.encode("utf-8")) > self.config.ws_max_message_bytes:
                        logger.debug("Closing WebSocket client %s: message exceeds size limit", ip)
                        session.close_code = status.WS_1009_MESSAGE_TOO_BIG
                        break

                    # Valid message received -> reset idle timeout
                    last_client_activity = time.monotonic()

                    if text == "ping":
                        try:
                            queue.put_nowait("pong")
                        except asyncio.QueueFull:
                            session.close_code = status.WS_1013_TRY_AGAIN_LATER
                            break
        except Exception as exc:
            logger.debug("Client reader loop error: %s", exc)
        finally:
            # Cleanup owns the reservation exactly once, including cancellation
            # before accept or while awaiting initial status. Shield it against
            # a second cancellation while the transport is closing.
            cleanup = asyncio.create_task(self._cleanup(websocket, ip, session))
            try:
                await asyncio.shield(cleanup)
            except asyncio.CancelledError:
                await cleanup
                raise

    async def _cleanup(self, websocket: WebSocket, ip: str, session: ClientSession | None) -> None:
        if session is not None:
            session.done_event.set()
            session.writer_task.cancel()
            await asyncio.gather(session.writer_task, return_exceptions=True)
        code = status.WS_1001_GOING_AWAY if not self._running else (
            session.close_code if session is not None else status.WS_1000_NORMAL_CLOSURE
        )
        try:
            await self._close(websocket, code)
        finally:
            async with self._lock:
                self._clients.pop(websocket, None)
                if self._handlers.pop(websocket, None) is not None:
                    self._total_reserved -= 1
                    self._ip_counts[ip] -= 1
                    if self._ip_counts[ip] == 0:
                        self._ip_counts.pop(ip)

    async def broadcast(self, message: dict[str, Any]) -> None:
        async with self._lock:
            sessions = list(self._clients.values())

        for session in sessions:
            if session.done_event.is_set():
                continue
            try:
                session.queue.put_nowait(message)
            except asyncio.QueueFull:
                # Slow client: outgoing queue is full (exceeded 2 unconsumed messages)
                logger.warning("Disconnecting slow WebSocket client %s (queue full)", session.ip)
                session.close_code = status.WS_1013_TRY_AGAIN_LATER
                session.done_event.set()

    async def _status_broadcast_loop(self, node: Node) -> None:
        while self._running:
            try:
                await asyncio.sleep(self.config.ws_status_interval)
                if not self._clients:
                    continue
                if node.state != "RUNNING":
                    continue
                status_data = await node.get_status()
                await self.broadcast({
                    "type": "node_status",
                    "payload": {
                        "height": status_data["height"],
                        "tip_hash": status_data["tip_hash"],
                        "pending_count": status_data["pending_count"],
                        "state": status_data["state"],
                        "peer_count": len(status_data["peers"]),
                    },
                })
            except asyncio.CancelledError:
                break
            except Exception as error:
                logger.error("Error in WebSocket broadcast loop: %s", error)
