"""Deterministic regressions for WebSocket ownership and cancellation."""

from __future__ import annotations

import asyncio
from types import SimpleNamespace

import pytest

from api.config import ApiConfig
from api.websocket.manager import WebSocketManager


class FakeNode:
    state = "RUNNING"

    def __init__(self, *, block_status=False):
        self.status_entered = asyncio.Event()
        self.status_gate = asyncio.Event()
        if not block_status:
            self.status_gate.set()

    async def get_status(self):
        self.status_entered.set()
        await self.status_gate.wait()
        return {
            "height": 0,
            "tip_hash": "0" * 64,
            "pending_count": 0,
            "state": self.state,
            "peers": [],
        }


class FakeWebSocket:
    def __init__(self, *, ip="127.0.0.1", block_accept=False, block_close=False):
        self.headers = {}
        self.client = SimpleNamespace(host=ip)
        self.accept_entered = asyncio.Event()
        self.accept_gate = asyncio.Event()
        self.accepted = asyncio.Event()
        self.receive_entered = asyncio.Event()
        self.close_entered = asyncio.Event()
        self.close_gate = asyncio.Event()
        self.send_entered = asyncio.Event()
        self.send_gate = asyncio.Event()
        self.block_message_type = None
        self.close_codes = []
        self.incoming = asyncio.Queue()
        self.outgoing = asyncio.Queue()
        if not block_accept:
            self.accept_gate.set()
        if not block_close:
            self.close_gate.set()
        self.send_gate.set()

    async def accept(self):
        self.accept_entered.set()
        await self.accept_gate.wait()
        self.accepted.set()

    async def receive(self):
        self.receive_entered.set()
        return await self.incoming.get()

    async def send_json(self, message):
        if message.get("type") == self.block_message_type:
            self.send_entered.set()
            await self.send_gate.wait()
        await self.outgoing.put(message)

    async def send_text(self, text):
        await self.outgoing.put(text)

    async def close(self, code=1000, reason=None):
        self.close_codes.append(code)
        self.close_entered.set()
        await self.close_gate.wait()
        self.disconnect()

    def disconnect(self):
        self.incoming.put_nowait({"type": "websocket.disconnect", "code": 1000})


def make_manager(*, cap=2, per_ip=2, queue_size=2):
    return WebSocketManager(ApiConfig(
        _env_file=None,
        ws_max_clients=cap,
        ws_max_clients_per_ip=per_ip,
        ws_client_queue_size=queue_size,
        # Background status updates must not determine test ordering.
        ws_status_interval=3600,
    ))


async def ready(websocket):
    message = await asyncio.wait_for(websocket.outgoing.get(), timeout=1)
    assert message["type"] == "node_status"
    await asyncio.wait_for(websocket.receive_entered.wait(), timeout=1)


def assert_empty(manager):
    assert manager.total_clients == 0
    assert manager._total_reserved == 0
    assert not manager._ip_counts


async def cleanup(manager, handlers, sockets):
    for websocket in sockets:
        websocket.accept_gate.set()
        websocket.close_gate.set()
        websocket.send_gate.set()
        websocket.disconnect()
    for handler in handlers:
        if not handler.done():
            handler.cancel()
    await asyncio.gather(*handlers, return_exceptions=True)
    await asyncio.wait_for(manager.stop(), timeout=3)


async def assert_no_background_tasks():
    # Let completed tasks deliver their callbacks before checking ownership.
    await asyncio.sleep(0)
    current = asyncio.current_task()
    assert not [task for task in asyncio.all_tasks() if task is not current]


@pytest.mark.parametrize("cancel_during", ["accept", "initial_status"])
def test_cancelled_handshake_or_initial_status_releases_slot(cancel_during):
    async def scenario():
        manager = make_manager(cap=1, per_ip=1)
        node = FakeNode(block_status=cancel_during == "initial_status")
        socket = FakeWebSocket(block_accept=cancel_during == "accept")
        replacement = FakeWebSocket()
        handlers = []
        await manager.start(node)
        try:
            handler = asyncio.create_task(manager.handle_connection(socket, node))
            handlers.append(handler)
            entered = socket.accept_entered if cancel_during == "accept" else node.status_entered
            await asyncio.wait_for(entered.wait(), timeout=1)
            assert manager._total_reserved == 1
            handler.cancel()
            await asyncio.wait_for(asyncio.gather(handler, return_exceptions=True), timeout=1)
            assert_empty(manager)

            # The same IP can reconnect immediately at a global/per-IP cap of 1.
            node.status_gate.set()
            new_handler = asyncio.create_task(manager.handle_connection(replacement, node))
            handlers.append(new_handler)
            await ready(replacement)
            assert replacement.accepted.is_set()
            assert manager.total_clients == 1
            replacement.disconnect()
            await asyncio.wait_for(new_handler, timeout=1)
            assert_empty(manager)
        finally:
            node.status_gate.set()
            await cleanup(manager, handlers, [socket, replacement])
        await assert_no_background_tasks()

    asyncio.run(scenario())


def test_stop_owns_active_reader_and_pending_handshake_and_is_idempotent():
    async def scenario():
        manager = make_manager()
        node = FakeNode()
        active = FakeWebSocket()
        pending = FakeWebSocket(block_accept=True)
        handlers = []
        await manager.start(node)
        try:
            handlers.append(asyncio.create_task(manager.handle_connection(active, node)))
            await ready(active)
            handlers.append(asyncio.create_task(manager.handle_connection(pending, node)))
            await asyncio.wait_for(pending.accept_entered.wait(), timeout=1)
            assert manager._total_reserved == 2

            await asyncio.wait_for(manager.stop(), timeout=1)
            await asyncio.wait_for(asyncio.gather(*handlers, return_exceptions=True), timeout=1)
            assert not pending.accepted.is_set()
            assert_empty(manager)
            await asyncio.wait_for(manager.stop(), timeout=1)
            assert_empty(manager)
            await assert_no_background_tasks()
        finally:
            await cleanup(manager, handlers, [active, pending])

    asyncio.run(scenario())


def test_stalled_rejection_close_does_not_hold_connection_lock():
    async def scenario():
        manager = make_manager(cap=2, per_ip=1)
        node = FakeNode()
        first = FakeWebSocket(ip="127.0.0.1")
        rejected = FakeWebSocket(ip="127.0.0.1", block_close=True)
        other_ip = FakeWebSocket(ip="127.0.0.2")
        sockets = [first, rejected, other_ip]
        handlers = []
        await manager.start(node)
        try:
            handlers.append(asyncio.create_task(manager.handle_connection(first, node)))
            await ready(first)
            handlers.append(asyncio.create_task(manager.handle_connection(rejected, node)))
            await asyncio.wait_for(rejected.close_entered.wait(), timeout=1)
            assert rejected.close_codes == [1008]
            assert not rejected.accepted.is_set()

            # A rejection whose transport cannot close must not block admission.
            handlers.append(asyncio.create_task(manager.handle_connection(other_ip, node)))
            await ready(other_ip)
            assert manager.total_clients == 2
            assert manager._total_reserved == 2
            assert not rejected.close_gate.is_set()
        finally:
            await cleanup(manager, handlers, sockets)
        assert_empty(manager)
        await assert_no_background_tasks()

    asyncio.run(scenario())


def test_stalled_writer_and_close_do_not_block_healthy_broadcasts():
    async def scenario():
        manager = make_manager()
        node = FakeNode()
        slow = FakeWebSocket(block_close=True)
        healthy = FakeWebSocket(ip="127.0.0.2")
        handlers = []
        await manager.start(node)
        try:
            for socket in [slow, healthy]:
                handlers.append(asyncio.create_task(manager.handle_connection(socket, node)))
                await ready(socket)
            slow.block_message_type = "test"
            slow.send_gate.clear()

            # One in-flight message plus a queue of two forces the slow client out.
            for sequence in range(4):
                message = {"type": "test", "sequence": sequence}
                await asyncio.wait_for(manager.broadcast(message), timeout=1)
                assert await asyncio.wait_for(healthy.outgoing.get(), timeout=1) == message
                if sequence == 0:
                    await asyncio.wait_for(slow.send_entered.wait(), timeout=1)

            await asyncio.wait_for(slow.close_entered.wait(), timeout=1)
            assert slow.close_codes[0] == 1013
            assert not slow.close_gate.is_set()
            message = {"type": "test", "sequence": 4}
            await asyncio.wait_for(manager.broadcast(message), timeout=1)
            assert await asyncio.wait_for(healthy.outgoing.get(), timeout=1) == message
        finally:
            await cleanup(manager, handlers, [slow, healthy])
        assert_empty(manager)
        await assert_no_background_tasks()

    asyncio.run(scenario())


def test_writer_failure_closes_transport_and_releases_reservation():
    async def scenario():
        manager = make_manager(cap=1, per_ip=1)
        node = FakeNode()
        socket = FakeWebSocket()

        async def fail_send(message):
            raise OSError("transport failure")

        socket.send_json = fail_send
        await manager.start(node)
        handler = asyncio.create_task(manager.handle_connection(socket, node))
        try:
            await asyncio.wait_for(handler, timeout=1)
            assert socket.close_codes == [1013]
            assert_empty(manager)
        finally:
            await cleanup(manager, [handler], [socket])
        await assert_no_background_tasks()

    asyncio.run(scenario())


def test_second_cancellation_during_close_still_finishes_cleanup():
    async def scenario():
        manager = make_manager(cap=1, per_ip=1)
        node = FakeNode()
        socket = FakeWebSocket(block_accept=True, block_close=True)
        await manager.start(node)
        handler = asyncio.create_task(manager.handle_connection(socket, node))
        try:
            await asyncio.wait_for(socket.accept_entered.wait(), timeout=1)
            handler.cancel()
            await asyncio.wait_for(socket.close_entered.wait(), timeout=1)
            handler.cancel()
            socket.close_gate.set()
            await asyncio.wait_for(asyncio.gather(handler, return_exceptions=True), timeout=1)
            assert_empty(manager)
        finally:
            await cleanup(manager, [handler], [socket])
        await assert_no_background_tasks()

    asyncio.run(scenario())
