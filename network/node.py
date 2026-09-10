"""Single-owner P2P node: validate and commit locally before best-effort relay."""

from __future__ import annotations

import asyncio
from collections import OrderedDict
from copy import deepcopy
from dataclasses import dataclass, field
import logging
import secrets
import time

from blockchain.block import Block
from blockchain.blockchain import Blockchain
from blockchain.genesis import GENESIS_HASH
from storage.codec import encode_block, encode_transaction
from storage.errors import StorageCorruptionError, StorageError
from transaction.transaction import Transaction
from network.config import NETWORK_ID, NodeConfig
from network.errors import (
    NetworkError, NodeBusyError, NodeClosedError, PeerDisconnectedError,
    PolicyLimitError, ProtocolError,
)
from network.messages import Message
from network.peer import PeerConnection, TokenBucket
from network.peer_manager import PeerManager
from network.protocol import (
    pack_block, pack_transaction, unpack_block, unpack_transaction,
)
from network.sync import SyncManager


logger = logging.getLogger(__name__)
_RESPONSES = {"GET_STATUS": "STATUS", "GET_PEERS": "PEERS",
              "GET_BLOCKS": "BLOCKS", "GET_MEMPOOL": "MEMPOOL"}


@dataclass
class PendingRequest:
    kind: str
    payload: dict
    deadline: float


@dataclass
class Session:
    peer: PeerConnection
    ready: asyncio.Future
    created: float
    service_bucket: TokenBucket
    endpoint: tuple[str, int] | None = None
    version_received: bool = False
    ack_received: bool = False
    remote_height: int = 0
    remote_tip: str = GENESIS_HASH
    pending: dict[str, PendingRequest] = field(default_factory=dict)
    expired: OrderedDict = field(default_factory=OrderedDict)
    next_status: float = 0.0
    next_discovery: float = 0.0
    next_mempool: float = 0.0
    next_export: float = 0.0
    next_ping: float = 0.0
    ping_nonce: str | None = None
    ping_deadline: float = 0.0
    sync_after: float = 0.0
    sync_state: str = "IDLE"
    error: str | None = None


@dataclass
class Event:
    kind: str
    value: object
    size: int
    future: asyncio.Future | None = None
    session_id: str | None = None


class Node:
    """A node owns its Blockchain and connection on one asyncio event loop.

    Successful admission means committed here, not acknowledged by all peers.
    This phase supports a single append-only branch, never fork replacement.
    """

    def __init__(self, config: NodeConfig, *, clock=time.monotonic):
        if not isinstance(config, NodeConfig):
            raise TypeError("config must be a NodeConfig")
        self.config = config
        self.node_id = secrets.token_hex(16)
        self.state = "CREATED"
        self.endpoint: tuple[str, int] | None = None
        self._clock = clock
        self._loop = None
        self._chain: Blockchain | None = None
        self._server = None
        self._dispatcher_task = None
        self._maintenance_task = None
        self._cleanup_task = None
        self._failure: BaseException | None = None
        self._events: asyncio.Queue[Event] = asyncio.Queue(maxsize=config.inbound_max_events)
        self._inbound_events = 0
        self._inbound_bytes = 0
        self._sessions: dict[str, Session] = {}
        self._dial_tasks: dict[tuple[str, int], asyncio.Task] = {}
        self._peer_closers: set[asyncio.Task] = set()
        self._closed_peers: set[str] = set()
        self._manager = PeerManager(config, clock=clock)
        self._sync = SyncManager(self)
        self._tick_queued = False
        self._counters = {"transactions_accepted": 0, "blocks_accepted": 0,
                          "messages_received": 0, "messages_enqueued": 0}

    def _ensure_loop(self):
        if self._loop is not asyncio.get_running_loop():
            raise RuntimeError("Node APIs must run on the event loop that started it")

    def _ensure_running(self):
        self._ensure_loop()
        if self.state == "FAILED" and isinstance(self._failure, StorageError):
            raise StorageError("Node storage failed; stop and open a new node") from self._failure
        if self.state != "RUNNING":
            raise NodeClosedError("Node is not running")

    async def start(self):
        if self.state != "CREATED":
            raise NodeClosedError("A Node instance can only be started once")
        self._loop = asyncio.get_running_loop()
        self.state = "STARTING"
        try:
            self._chain = Blockchain(
                db_path=self.config.db_path,
                mempool_max_transactions=self.config.mempool_max_transactions,
                mempool_max_bytes=self.config.mempool_max_bytes,
            )
            self._server = await asyncio.start_server(
                self._accepted_socket, self.config.host, self.config.port,
                limit=min(self.config.max_frame_bytes, 64 * 1024),
                start_serving=False,
            )
            address = self._server.sockets[0].getsockname()
            self.endpoint = (address[0], address[1])
            self._manager.set_self_endpoint(self.endpoint)
            self.state = "RUNNING"
            self._dispatcher_task = asyncio.create_task(
                self._dispatch_loop(), name=f"node-dispatch-{self.node_id}")
            self._maintenance_task = asyncio.create_task(
                self._maintenance_loop(), name=f"node-timer-{self.node_id}")
            await self._server.start_serving()
            for endpoint in self.config.seeds:
                self._manager.add_candidate(endpoint, seed=True)
            logger.info("node started id=%s endpoint=%s storage=%s", self.node_id,
                        self.endpoint, "sqlite" if self.config.db_path is not None else "ram")
        except BaseException as error:
            self._failure = error
            self.state = "FAILED"
            await asyncio.shield(self._begin_stop())
            raise

    async def stop(self):
        if self._loop is None:
            self._loop = asyncio.get_running_loop()
        self._ensure_loop()
        await asyncio.shield(self._begin_stop())

    def _begin_stop(self):
        if self._cleanup_task is None:
            if self.state != "FAILED":
                self.state = "STOPPING"
            self._cleanup_task = asyncio.create_task(
                self._cleanup(), name=f"node-cleanup-{self.node_id}")
        return self._cleanup_task

    def _fatal(self, error):
        if self.state in {"STOPPING", "STOPPED", "FAILED"}:
            return
        self._failure = error
        self.state = "FAILED"
        logger.error("node failed id=%s reason=%s", self.node_id, type(error).__name__)
        self._begin_stop()

    async def _cleanup(self):
        # The supervisor, not the dispatcher, joins/cancels owned tasks.
        if self._server is not None:
            self._server.close()
        tasks = [t for t in (self._maintenance_task, self._dispatcher_task)
                 if t is not None]
        tasks.extend(self._dial_tasks.values())
        for task in tasks:
            if not task.done():
                task.cancel()
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)
        peers = [s.peer for s in self._sessions.values()]
        if peers:
            await asyncio.gather(*(p.close() for p in peers), return_exceptions=True)
        if self._peer_closers:
            await asyncio.gather(*list(self._peer_closers), return_exceptions=True)
        if self._server is not None:
            await self._server.wait_closed()
        while not self._events.empty():
            event = self._events.get_nowait()
            self._release(event.size)
            if event.future is not None and not event.future.done():
                event.future.set_exception(NodeClosedError("Node stopped before command was processed"))
            self._events.task_done()
        for session in self._sessions.values():
            if not session.ready.done():
                session.ready.set_result(False)
            session.pending.clear()
        self._sessions.clear()
        self._closed_peers.clear()
        self._dial_tasks.clear()
        self._sync.clear()
        self._tick_queued = False
        try:
            if self._chain is not None:
                self._chain.close()
        except Exception as error:
            if self._failure is None:
                self._failure = error
            self.state = "FAILED"
            logger.error("node storage cleanup failed id=%s", self.node_id)
        if self.state != "FAILED":
            self.state = "STOPPED"
        logger.info("node stopped id=%s state=%s", self.node_id, self.state)

    def _reserve(self, size):
        if (self.state != "RUNNING" or self._inbound_events >= self.config.inbound_max_events
                or self._inbound_bytes + size > self.config.inbound_max_bytes):
            return False
        self._inbound_events += 1
        self._inbound_bytes += size
        return True

    def _release(self, size):
        self._inbound_events -= 1
        self._inbound_bytes -= size
        if self._inbound_events < 0 or self._inbound_bytes < 0:
            raise RuntimeError("Node inbound reservation accounting underflow")

    async def _call(self, kind, value=None, *, size=1):
        self._ensure_running()
        if not self._reserve(size):
            raise NodeBusyError("Node inbound command budget is full")
        future = self._loop.create_future()
        try:
            self._events.put_nowait(Event(kind, value, size, future))
        except BaseException:
            self._release(size)
            raise
        return await future

    async def submit_transaction(self, transaction):
        self._ensure_running()
        if not isinstance(transaction, Transaction):
            return False
        try:
            snapshot = deepcopy(transaction)
            data = encode_transaction(snapshot)
        except (StorageCorruptionError, TypeError, ValueError, AttributeError, RecursionError):
            return False
        return await self._call("submit", snapshot, size=len(data) + 4)

    async def accept_block(self, block):
        self._ensure_running()
        if not isinstance(block, Block):
            return False
        try:
            snapshot = deepcopy(block)
            data = encode_block(snapshot)
        except (StorageCorruptionError, TypeError, ValueError, AttributeError, RecursionError):
            return False
        return await self._call("block", snapshot, size=len(data) + 4)

    async def get_status(self):
        return await self._call("status")

    async def get_block_by_height(self, height):
        return await self._call("get_block", height)

    async def get_balance(self, address):
        return await self._call("balance", address)

    async def get_pending_transactions(self):
        return await self._call("pending")

    async def validate_chain(self):
        return await self._call("validate")

    async def create_mempool_block_template(self, miner_address, *, timestamp=None,
                                          max_transactions=100, max_bytes=100000):
        return await self._call("template", (miner_address, {
            "timestamp": timestamp, "max_transactions": max_transactions,
            "max_bytes": max_bytes,
        }))

    async def connect(self, host, port):
        self._ensure_running()
        endpoint = self.config.validate_endpoint(host, port)
        if endpoint == self.endpoint:
            raise PeerDisconnectedError("Cannot connect a node to itself")
        for session in self._sessions.values():
            if session.endpoint == endpoint and not session.peer.closed:
                if await asyncio.shield(session.ready):
                    return session.peer
        task = self._dial_tasks.get(endpoint)
        if task is None:
            if (len(self._sessions) + len(self._dial_tasks) >= self.config.max_peers
                    or len(self._dial_tasks) >= self.config.max_concurrent_dials):
                raise NodeBusyError("Peer or concurrent dial slots are full")
            self._manager.add_candidate(endpoint)
            self._manager.mark_attempt(endpoint)
            task = asyncio.create_task(self._dial(endpoint), name=f"node-dial-{endpoint}")
            self._dial_tasks[endpoint] = task
            task.add_done_callback(lambda completed, address=endpoint: self._dial_done(address, completed))
        return await asyncio.shield(task)

    def _dial_done(self, endpoint, task):
        if self._dial_tasks.get(endpoint) is task:
            self._dial_tasks.pop(endpoint, None)
        if not task.cancelled():
            # Retrieving background dial errors avoids unhandled-task warnings;
            # explicit callers awaiting the same task still receive the error.
            task.exception()

    async def _dial(self, endpoint):
        session = None
        writer = None
        try:
            reader, writer = await asyncio.wait_for(asyncio.open_connection(
                *endpoint, limit=min(self.config.max_frame_bytes, 64 * 1024)),
                timeout=self.config.connect_timeout)
            if self.state != "RUNNING":
                raise NodeClosedError("Node stopped during connect")
            session = self._attach(reader, writer, outbound=True, endpoint=endpoint)
            ready = await asyncio.wait_for(asyncio.shield(session.ready),
                                           timeout=self.config.handshake_timeout)
            if not ready or session.peer.closed:
                # A deterministic duplicate winner can replace this socket.
                winner = next((s.peer for s in self._sessions.values()
                               if s.endpoint == endpoint and s.peer.established and not s.peer.closed), None)
                if winner is not None:
                    return winner
                raise PeerDisconnectedError("Peer handshake failed")
            return session.peer
        except BaseException:
            self._manager.mark_disconnected(endpoint)
            if session is not None:
                await session.peer.close()
            elif writer is not None:
                writer.close()
                try:
                    await asyncio.wait_for(writer.wait_closed(), self.config.close_timeout)
                except (OSError, TimeoutError):
                    pass
            raise

    def _accepted_socket(self, reader, writer):
        remote = writer.get_extra_info("peername")
        try:
            if (self.state != "RUNNING" or remote is None
                    or len(self._sessions) + len(self._dial_tasks) >= self.config.max_peers):
                raise NodeBusyError("No inbound peer slot")
            self.config.validate_host(remote[0])
        except (ValueError, NetworkError):
            writer.close()
            return
        try:
            self._attach(reader, writer, outbound=False)
        except Exception as error:
            writer.close()
            self._fatal(error)

    def _attach(self, reader, writer, *, outbound, endpoint=None):
        peer = PeerConnection(reader, writer, config=self.config, outbound=outbound,
                              on_message=self._on_message, on_close=self._on_close,
                              reserve=self._reserve, release=self._release, clock=self._clock)
        now = self._clock()
        session = Session(peer, self._loop.create_future(), now,
                          TokenBucket(self.config.service_rate, self.config.service_burst, clock=self._clock),
                          endpoint=endpoint, next_ping=now + self.config.ping_interval)
        self._sessions[peer.connection_id] = session
        height, tip = self._tip()
        self._send(session, Message("VERSION", {
            "network_id": NETWORK_ID, "genesis_hash": GENESIS_HASH,
            "node_id": self.node_id, "connection_nonce": peer.connection_nonce,
            "listen_port": self.endpoint[1], "height": height, "tip_hash": tip,
        }))
        peer.start()
        return session

    def _on_message(self, peer, message, size):
        if self.state != "RUNNING" or peer.connection_id not in self._sessions:
            return False
        self._events.put_nowait(Event("remote", message, size, session_id=peer.connection_id))
        return True

    def _on_close(self, peer):
        # Bounded by peer slots and reclaimed on every dispatcher turn/tick.
        self._closed_peers.add(peer.connection_id)
        session = self._sessions.get(peer.connection_id)
        if session is not None and not session.ready.done():
            session.ready.set_result(False)
        if peer.unexpected_error is not None:
            self._fatal(peer.unexpected_error)

    def _close_peer(self, session):
        if session.peer.closed:
            return
        # Mark now: no more state from an already rejected connection.
        session.peer.closed = True
        task = asyncio.create_task(session.peer.close())
        self._peer_closers.add(task)
        task.add_done_callback(self._peer_closers.discard)

    def _reap_peers(self):
        for connection_id in list(self._closed_peers):
            self._closed_peers.discard(connection_id)
            session = self._sessions.pop(connection_id, None)
            if session is None:
                continue
            self._sync.disconnected(connection_id)
            session.pending.clear()
            if session.endpoint is not None and not any(
                    s.endpoint == session.endpoint and s.peer.established and not s.peer.closed
                    for s in self._sessions.values()):
                self._manager.mark_disconnected(session.endpoint)

    def _tip(self):
        return self._chain.height, self._chain.get_latest_block().hash()

    def _status_payload(self):
        height, tip = self._tip()
        return {"height": height, "tip_hash": tip}

    def _status(self):
        return dict(self._status_payload(), state=self.state,
                    pending_count=self._chain.get_mempool_stats()[0],
                    peers=[{"node_id": s.peer.node_id, "endpoint": s.endpoint,
                            "sync_state": s.sync_state, "error": s.error,
                            "height": s.remote_height, "tip_hash": s.remote_tip}
                           for s in self._sessions.values()
                           if s.peer.established and not s.peer.closed],
                    counters=dict(self._counters),
                    inbound_events=self._inbound_events, inbound_bytes=self._inbound_bytes)

    def _send(self, session, message):
        if self.state != "RUNNING" or session.peer.closed:
            return False
        result = session.peer.send(message)
        if result:
            self._counters["messages_enqueued"] += 1
        return result

    def _broadcast(self, message, *, source=None):
        for session in list(self._sessions.values()):
            if session is not source and session.peer.established:
                try:
                    self._send(session, message)
                except PolicyLimitError:
                    logger.warning("propagation policy limit type=%s", message.type)

    def _submit_transaction(self, transaction, *, source=None):
        accepted = self._chain.submit_transaction(transaction)
        if accepted:
            self._counters["transactions_accepted"] += 1
            try:
                encoded = pack_transaction(transaction, max_item_bytes=self.config.max_item_bytes)
                self._broadcast(Message("NEW_TRANSACTION", {"transaction": encoded}), source=source)
            except PolicyLimitError:
                logger.warning("transaction accepted locally but exceeds relay policy")
        return accepted

    def _accept_block(self, block, *, source=None):
        if block.previous_block_hash != self._tip()[1]:
            if source is not None and self._chain.get_block_by_hash(block.hash()) is None:
                self._request(source, "GET_STATUS", {})
            return False
        accepted = self._chain.add_block(block)
        if accepted:
            self._counters["blocks_accepted"] += 1
            self._sync.tip_changed()
            try:
                encoded = pack_block(block, max_item_bytes=self.config.max_item_bytes)
                self._broadcast(Message("NEW_BLOCK", {"block": encoded}), source=source)
            except PolicyLimitError:
                logger.warning("block accepted locally but exceeds relay policy")
            self._broadcast(Message("STATUS", self._status_payload()))
        return accepted

    def _has_request(self, session, kind):
        return any(request.kind == kind for request in session.pending.values())

    def _request(self, session, kind, payload):
        if (not session.peer.established or session.peer.closed
                or len(session.pending) >= self.config.max_requests
                or self._has_request(session, kind)):
            return None
        request_id = secrets.token_hex(16)
        if self._send(session, Message(kind, payload, request_id)):
            session.pending[request_id] = PendingRequest(
                kind, dict(payload), self._clock() + self.config.request_timeout)
            return request_id
        return None

    def _error(self, session, request_id, code):
        self._send(session, Message("ERROR", {"code": code, "message": code}, request_id))

    def _expire(self, session, request_id):
        session.expired[request_id] = self._clock() + 60.0
        while len(session.expired) > 64:
            session.expired.popitem(last=False)

    def _connection_rank(self, session):
        initiator = self.node_id if session.peer.outbound else session.peer.node_id
        return (initiator, tuple(sorted((session.peer.connection_nonce, session.peer.remote_nonce))))

    def _handshake(self, session, message):
        peer = session.peer
        if message.type == "VERSION":
            payload = message.payload
            if session.version_received:
                raise ProtocolError("Repeated VERSION")
            if payload["network_id"] != NETWORK_ID or payload["genesis_hash"] != GENESIS_HASH:
                raise ProtocolError("Wrong network/genesis")
            if payload["node_id"] == self.node_id:
                raise ProtocolError("Self connection")
            if payload["height"] == 0 and payload["tip_hash"] != GENESIS_HASH:
                raise ProtocolError("Invalid genesis tip")
            endpoint = self.config.validate_endpoint(peer.endpoint[0], payload["listen_port"])
            session.endpoint = endpoint
            peer.node_id, peer.remote_nonce = payload["node_id"], payload["connection_nonce"]
            session.remote_height, session.remote_tip = payload["height"], payload["tip_hash"]
            session.version_received = True
            self._send(session, Message("VERACK", {}))
        elif message.type == "VERACK":
            if not session.version_received or session.ack_received:
                raise ProtocolError("Unexpected VERACK")
            session.ack_received = True
        else:
            raise ProtocolError("Application message before handshake")
        if session.version_received and session.ack_received and not peer.closed:
            duplicates = [s for s in self._sessions.values()
                          if s is not session and s.peer.node_id == peer.node_id
                          and s.version_received and not s.peer.closed]
            winner = min([session, *duplicates], key=self._connection_rank)
            for duplicate in [session, *duplicates]:
                if duplicate is not winner:
                    self._close_peer(duplicate)
            if winner is not session:
                return
            peer.established = True
            self._manager.mark_connected(session.endpoint)
            if not session.ready.done():
                session.ready.set_result(True)
            logger.info("peer established node=%s peer=%s", self.node_id, peer.node_id)

    def _remote(self, session, message):
        self._counters["messages_received"] += 1
        if not session.peer.established:
            self._handshake(session, message)
            return
        if message.type in {"VERSION", "VERACK"}:
            raise ProtocolError("Repeated handshake")
        if message.type == "PING":
            self._send(session, Message("PONG", dict(message.payload)))
            return
        if message.type == "PONG":
            if session.ping_nonce != message.payload["nonce"]:
                raise ProtocolError("PONG does not match outstanding nonce")
            session.ping_nonce = None
            return
        if message.type in _RESPONSES:
            if message.type in {"GET_BLOCKS", "GET_MEMPOOL"} and not session.service_bucket.consume():
                self._error(session, message.request_id, "BUSY")
            elif message.type == "GET_STATUS":
                self._send(session, Message("STATUS", self._status_payload(), message.request_id))
            elif message.type == "GET_PEERS":
                endpoints = [endpoint for endpoint in self._manager.known_endpoints
                             if endpoint not in {self.endpoint, session.endpoint}][:32]
                self._send(session, Message("PEERS", {
                    "peers": [{"host": host, "port": port} for host, port in endpoints],
                }, message.request_id))
            elif message.type == "GET_BLOCKS":
                self._sync.serve_blocks(session, message)
            elif message.type == "GET_MEMPOOL":
                self._sync.serve_mempool(session, message)
            return
        request = None
        if message.request_id is not None:
            request = session.pending.pop(message.request_id, None)
            if request is None:
                if message.request_id in session.expired:
                    return
                raise ProtocolError("Unsolicited response ID")
            self._expire(session, message.request_id)
            if message.type not in {_RESPONSES[request.kind], "ERROR"}:
                raise ProtocolError("Response type does not match request")
        if message.type == "ERROR":
            if request is not None:
                self._sync.failed_request(session, request, message.payload["code"])
            return
        if message.type == "STATUS":
            if message.payload["height"] == 0 and message.payload["tip_hash"] != GENESIS_HASH:
                raise ProtocolError("Invalid genesis status")
            session.remote_height = message.payload["height"]
            session.remote_tip = message.payload["tip_hash"]
        elif message.type == "PEERS":
            for endpoint in message.payload["peers"]:
                try:
                    self._manager.add_candidate((endpoint["host"], endpoint["port"]))
                except ValueError:
                    continue
        elif message.type == "NEW_TRANSACTION":
            tx = unpack_transaction(message.payload["transaction"], max_item_bytes=self.config.max_item_bytes)
            self._submit_transaction(tx, source=session)
        elif message.type == "NEW_BLOCK":
            block = unpack_block(message.payload["block"], max_item_bytes=self.config.max_item_bytes)
            self._accept_block(block, source=session)
        elif message.type == "BLOCKS":
            self._sync.receive_blocks(session, request, message)
        elif message.type == "MEMPOOL":
            self._sync.receive_mempool(session, request, message)
        else:
            raise ProtocolError("Unexpected message")

    def _command(self, event):
        if event.kind == "submit":
            return self._submit_transaction(event.value)
        if event.kind == "block":
            return self._accept_block(event.value)
        if event.kind == "status":
            return self._status()
        if event.kind == "get_block":
            return self._chain.get_block_by_height(event.value)
        if event.kind == "balance":
            return self._chain.get_balance(event.value)
        if event.kind == "pending":
            return self._chain.mempool.get_transactions()
        if event.kind == "validate":
            return self._chain.validate_chain()
        if event.kind == "template":
            return self._chain.create_mempool_block_template(event.value[0], **event.value[1])
        raise RuntimeError("Unknown local command")

    async def _dispatch_loop(self):
        while self.state == "RUNNING":
            event = await self._events.get()
            try:
                self._reap_peers()
                if event.future is not None and event.future.cancelled():
                    continue
                if event.kind == "tick":
                    self._tick_queued = False
                    self._tick()
                    result = None
                elif event.kind == "remote":
                    session = self._sessions.get(event.session_id)
                    if session is None or session.peer.closed:
                        continue
                    try:
                        self._remote(session, event.value)
                    except (ProtocolError, PolicyLimitError, ValueError) as error:
                        session.error = type(error).__name__
                        logger.info("peer rejected connection=%s reason=%s", event.session_id,
                                    type(error).__name__)
                        self._close_peer(session)
                    result = None
                else:
                    try:
                        result = self._command(event)
                    except (TypeError, ValueError, NetworkError) as error:
                        if not event.future.done():
                            event.future.set_exception(error)
                        continue
                if event.future is not None and not event.future.done():
                    event.future.set_result(result)
            except Exception as error:
                if event.future is not None and not event.future.done():
                    event.future.set_exception(error)
                self._fatal(error)
            finally:
                self._release(event.size)
                self._events.task_done()
            await asyncio.sleep(0)

    async def _maintenance_loop(self):
        try:
            while self.state == "RUNNING":
                if not self._tick_queued and self._reserve(1):
                    self._tick_queued = True
                    self._events.put_nowait(Event("tick", None, 1))
                await asyncio.sleep(self.config.maintenance_interval)
        except asyncio.CancelledError:
            raise
        except Exception as error:
            self._fatal(error)

    def _tick(self):
        now = self._clock()
        for session in list(self._sessions.values()):
            if session.peer.closed:
                continue
            if not session.peer.established:
                if now - session.created >= self.config.handshake_timeout:
                    self._close_peer(session)
                continue
            for request_id, request in list(session.pending.items()):
                if now >= request.deadline:
                    session.pending.pop(request_id)
                    self._expire(session, request_id)
                    self._sync.failed_request(session, request, "TIMEOUT")
            for request_id, expiry in list(session.expired.items()):
                if now >= expiry:
                    session.expired.pop(request_id)
            if session.ping_nonce is not None and now >= session.ping_deadline:
                self._close_peer(session)
                continue
            if session.ping_nonce is None and now >= session.next_ping:
                session.ping_nonce = secrets.token_hex(16)
                session.ping_deadline = now + self.config.pong_timeout
                session.next_ping = now + self.config.ping_interval
                self._send(session, Message("PING", {"nonce": session.ping_nonce}))
            if now >= session.next_status:
                self._request(session, "GET_STATUS", {})
                session.next_status = now + self.config.status_interval
            if now >= session.next_discovery:
                self._request(session, "GET_PEERS", {})
                session.next_discovery = now + self.config.discovery_interval
        self._sync.tick(now)
        for endpoint in self._manager.due_candidates():
            if (endpoint == self.endpoint or endpoint in self._dial_tasks
                    or any(s.endpoint == endpoint and not s.peer.closed for s in self._sessions.values())):
                continue
            if (len(self._sessions) + len(self._dial_tasks) >= self.config.max_peers
                    or len(self._dial_tasks) >= self.config.max_concurrent_dials):
                break
            self._manager.mark_attempt(endpoint)
            task = asyncio.create_task(self._dial(endpoint), name=f"node-seed-{endpoint}")
            self._dial_tasks[endpoint] = task
            task.add_done_callback(lambda completed, address=endpoint: self._dial_done(address, completed))
