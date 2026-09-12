"""Transport bounds and candidate policy, using asyncio.run and loopback only."""

import asyncio
import pytest

from network.config import NodeConfig
from network.errors import NodeBusyError, NodeClosedError, PeerDisconnectedError, PolicyLimitError, ProtocolError
from network.messages import Message
from network.peer import PeerConnection, TokenBucket
from network.peer_manager import PeerManager
from network.protocol import decode_message, encode_message


def ping(number=0):
    return Message("PING", {"nonce": f"{number:032x}"})


class Clock:
    def __init__(self):
        self.now = 0.0

    def __call__(self):
        return self.now


class NoJitter:
    def uniform(self, low, high):
        return 1.0


class Budget:
    def __init__(self, max_frames=128, max_bytes=16 * 1024 * 1024):
        self.frames = 0
        self.bytes = 0
        self.max_frames = max_frames
        self.max_bytes = max_bytes
        self.reservations = []

    def reserve(self, size):
        self.reservations.append(size)
        if self.frames >= self.max_frames or self.bytes + size > self.max_bytes:
            return False
        self.frames += 1
        self.bytes += size
        return True

    def release(self, size):
        self.frames -= 1
        self.bytes -= size
        assert self.frames >= 0 and self.bytes >= 0


class Writer:
    """An in-memory stream with independently controllable drain and close."""

    def __init__(self, *, stalled=False, stalled_close=False, fail_write=False):
        self.frames = []
        self.drain_started = asyncio.Event()
        self.drain_gate = asyncio.Event()
        self.close_gate = asyncio.Event()
        if not stalled:
            self.drain_gate.set()
        if not stalled_close:
            self.close_gate.set()
        self.close_calls = 0
        self.abort_calls = 0
        self.fail_write = fail_write
        self.transport = self

    def get_extra_info(self, name):
        return ("127.0.0.1", 5100) if name == "peername" else None

    def write(self, frame):
        if self.fail_write:
            raise ConnectionResetError("test reset")
        self.frames.append(frame)

    async def drain(self):
        self.drain_started.set()
        await self.drain_gate.wait()

    def close(self):
        self.close_calls += 1

    async def wait_closed(self):
        await self.close_gate.wait()

    def abort(self):
        self.abort_calls += 1


async def until(predicate):
    async def poll():
        while not predicate():
            await asyncio.sleep(0)
    await asyncio.wait_for(poll(), timeout=2)


def make_peer(*, config=None, writer=None, budget=None, on_message=None, clock=None):
    received = []
    closed = []
    budget = budget or Budget()

    def receive(peer, message, size):
        received.append((message, size))
        return False

    kwargs = {} if clock is None else {"clock": clock}
    peer = PeerConnection(
        asyncio.StreamReader(), writer or Writer(), config=config or NodeConfig(),
        on_message=on_message or receive, on_close=closed.append,
        reserve=budget.reserve, release=budget.release, **kwargs,
    )
    return peer, budget, received, closed


def test_token_bucket_refills_caps_and_rejects_clock_regression():
    clock = Clock()
    bucket = TokenBucket(10, 20, clock=clock)
    assert bucket.consume(20)
    assert not bucket.consume()
    clock.now = 0.5
    assert bucket.consume(5)
    clock.now = 0.25
    assert not bucket.consume()
    clock.now = 0.5
    assert not bucket.consume()
    clock.now = 100
    assert not bucket.consume(21)
    assert bucket.consume(20)
    with pytest.raises(ValueError):
        bucket.consume(-1)


def test_partial_prefix_body_and_coalesced_frames():
    async def scenario():
        peer, budget, received, closed = make_peer()
        peer.start()
        first, second = encode_message(ping(1)), encode_message(ping(2))
        peer.reader.feed_data(first[:2])
        await asyncio.sleep(0)
        assert budget.frames == 0
        peer.reader.feed_data(first[2:8])
        await until(lambda: budget.frames == 1)
        assert budget.bytes == len(first)
        peer.reader.feed_data(first[8:] + second)
        await until(lambda: len(received) == 2)
        assert [message for message, _ in received] == [ping(1), ping(2)]
        assert [size for _, size in received] == [len(first), len(second)]
        assert budget.bytes == budget.frames == 0
        await peer.close()
        assert closed == [peer]
    asyncio.run(scenario())


def test_owned_reservations_remain_until_dispatcher_releases():
    async def scenario():
        events = []

        def receive(peer, message, size):
            events.append((message, size))
            return True

        peer, budget, _, _ = make_peer(on_message=receive)
        frame = encode_message(ping())
        peer.start()
        peer.reader.feed_data(frame)
        await until(lambda: len(events) == 1)
        assert budget.frames == 1 and budget.bytes == len(frame)
        await peer.close()
        assert budget.bytes == len(frame)
        budget.release(events[0][1])
        assert budget.frames == budget.bytes == 0
    asyncio.run(scenario())


@pytest.mark.parametrize("prefix", [0, 1025, 2**32 - 1])
def test_bad_length_rejected_before_body_reservation(prefix):
    async def scenario():
        peer, budget, received, _ = make_peer(config=NodeConfig(max_frame_bytes=1024))
        peer.start()
        peer.reader.feed_data(prefix.to_bytes(4, "big"))
        await until(lambda: peer.closed)
        await peer.close()
        assert not received and not budget.reservations
        assert peer.unexpected_error is None
    asyncio.run(scenario())


@pytest.mark.parametrize("sent_bytes", [2, 5, 12])
def test_truncated_frames_release_reservation(sent_bytes):
    async def scenario():
        peer, budget, received, _ = make_peer()
        peer.start()
        peer.reader.feed_data(encode_message(ping())[:sent_bytes])
        peer.reader.feed_eof()
        await until(lambda: peer.closed)
        await peer.close()
        assert not received and budget.frames == budget.bytes == 0
        assert peer.unexpected_error is None
    asyncio.run(scenario())


@pytest.mark.parametrize("body", [b"{}", b"\xff", b"{\"version\":1,\"version\":1}"])
def test_malformed_envelope_closes_only_transport_and_releases_budget(body):
    async def scenario():
        peer, budget, received, _ = make_peer()
        peer.start()
        peer.reader.feed_data(len(body).to_bytes(4, "big") + body)
        await until(lambda: peer.closed)
        await peer.close()
        assert not received and budget.frames == budget.bytes == 0
        assert peer.unexpected_error is None
    asyncio.run(scenario())


def test_global_budget_refuses_before_body_read():
    async def scenario():
        peer, budget, _, _ = make_peer(budget=Budget(max_bytes=10))
        peer.start()
        peer.reader.feed_data((1000).to_bytes(4, "big"))
        await until(lambda: peer.closed)
        await peer.close()
        assert budget.reservations == [1004]
        assert budget.frames == budget.bytes == 0
        assert peer.close_reason == "global inbound queue limit"
    asyncio.run(scenario())


@pytest.mark.parametrize("body_started", [False, True])
def test_header_and_body_timeout_release_budget(body_started):
    async def scenario():
        peer, budget, _, _ = make_peer(
            config=NodeConfig(read_timeout=0.02, body_timeout=0.02)
        )
        peer.start()
        if body_started:
            peer.reader.feed_data((100).to_bytes(4, "big") + b"{")
        await until(lambda: peer.closed)
        await peer.close()
        assert budget.frames == budget.bytes == 0
        assert peer.close_reason == "TimeoutError"
    asyncio.run(scenario())


@pytest.mark.parametrize("byte_limit", [False, True])
def test_incoming_message_and_wire_byte_rate_caps(byte_limit):
    async def scenario():
        frame = encode_message(ping())
        config = NodeConfig(message_burst=2) if not byte_limit else NodeConfig(
            byte_burst=2 * len(frame)
        )
        peer, budget, received, _ = make_peer(config=config, clock=Clock())
        peer.start()
        peer.reader.feed_data(frame * 3)
        await until(lambda: peer.closed)
        await peer.close()
        assert len(received) == 2
        assert budget.frames == budget.bytes == 0
        assert peer.close_reason == "ProtocolError"
    asyncio.run(scenario())


def test_one_writer_preserves_fifo_across_producers():
    async def scenario():
        peer, _, _, _ = make_peer()
        peer.start()

        async def produce(number):
            assert peer.send(ping(number))

        await asyncio.gather(*(produce(number) for number in range(30)))
        await until(lambda: peer.outbound_frames == 0)
        assert [decode_message(frame[4:]) for frame in peer.writer.frames] == [
            ping(number) for number in range(30)
        ]
        assert peer.outbound_bytes == 0
        await peer.close()
    asyncio.run(scenario())


@pytest.mark.parametrize("byte_limit", [False, True])
def test_outbound_overflow_counts_inflight_and_does_not_block(byte_limit):
    async def scenario():
        frame = encode_message(ping())
        config = NodeConfig(outbound_max_frames=2) if not byte_limit else NodeConfig(
            outbound_max_bytes=2 * len(frame)
        )
        writer = Writer(stalled=True)
        peer, _, _, closed = make_peer(config=config, writer=writer)
        peer.start()
        assert peer.send(ping())
        await asyncio.wait_for(writer.drain_started.wait(), 2)
        assert peer.outbound_frames == 1 and peer.outbound_bytes == len(frame)
        assert peer.send(ping(1))
        assert not peer.send(ping(2))
        assert peer.closed and not peer.send(ping(3))
        await peer.close()
        assert peer.outbound_frames == peer.outbound_bytes == 0
        assert len(writer.frames) == 1 and closed == [peer]
    asyncio.run(scenario())


def test_slow_peer_does_not_delay_other_peer():
    async def scenario():
        slow, _, _, _ = make_peer(writer=Writer(stalled=True))
        fast, _, _, _ = make_peer()
        slow.start()
        fast.start()
        assert slow.send(ping()) and fast.send(ping())
        await until(lambda: bool(fast.writer.frames) and fast.outbound_frames == 0)
        assert slow.outbound_frames == 1
        await asyncio.gather(slow.close(), fast.close())
    asyncio.run(scenario())


@pytest.mark.parametrize("fail_write", [False, True])
def test_write_timeout_or_socket_error_cleans_entire_queue(fail_write):
    async def scenario():
        peer, budget, _, _ = make_peer(
            writer=Writer(stalled=True, fail_write=fail_write),
            config=NodeConfig(write_timeout=0.02),
        )
        peer.start()
        assert peer.send(ping()) and peer.send(ping(1))
        await until(lambda: peer.closed)
        await peer.close()
        assert peer.outbound_frames == peer.outbound_bytes == 0
        assert budget.frames == budget.bytes == 0
        assert peer.unexpected_error is None
    asyncio.run(scenario())


def test_close_timeout_aborts_transport():
    async def scenario():
        writer = Writer(stalled_close=True)
        peer, _, _, closed = make_peer(
            writer=writer, config=NodeConfig(close_timeout=0.02)
        )
        await peer.close()
        assert writer.abort_calls == 1 and closed == [peer]
    asyncio.run(scenario())


def test_unexpected_socket_cleanup_failure_is_visible_to_owner():
    async def scenario():
        error = RuntimeError("injected wait_closed failure")

        class BrokenClose(Writer):
            async def wait_closed(self):
                raise error

        writer = BrokenClose()
        peer, _, _, closed = make_peer(writer=writer)
        await peer.close()
        assert peer.unexpected_error is error
        assert writer.abort_calls == 1 and closed == [peer]
    asyncio.run(scenario())


@pytest.mark.parametrize("cancel_reader", [False, True])
def test_task_cancellation_releases_partial_read_and_inflight_write(cancel_reader):
    async def scenario():
        writer = Writer(stalled=True)
        peer, budget, _, _ = make_peer(writer=writer)
        peer.start()
        peer.reader.feed_data((1000).to_bytes(4, "big") + b"{")
        assert peer.send(ping()) and peer.send(ping(1))
        await until(lambda: budget.frames == 1 and writer.drain_started.is_set())
        (peer.reader_task if cancel_reader else peer.writer_task).cancel()
        await until(lambda: peer.closed)
        await peer.close()
        assert peer.reader_task.done() and peer.writer_task.done()
        assert budget.frames == budget.bytes == 0
        assert peer.outbound_frames == peer.outbound_bytes == 0
    asyncio.run(scenario())


def test_concurrent_close_shares_cleanup_despite_cancelled_caller():
    async def scenario():
        writer = Writer(stalled_close=True)
        peer, budget, _, closed = make_peer(writer=writer)
        peer.start()
        peer.reader.feed_data((1000).to_bytes(4, "big"))
        await until(lambda: budget.frames == 1)
        first = asyncio.create_task(peer.close())
        second = asyncio.create_task(peer.close())
        await until(lambda: writer.close_calls == 1)
        first.cancel()
        with pytest.raises(asyncio.CancelledError):
            await first
        assert not second.done()
        writer.close_gate.set()
        await asyncio.wait_for(second, 2)
        await peer.close()
        assert writer.close_calls == 1 and closed == [peer]
        assert budget.frames == budget.bytes == 0
    asyncio.run(scenario())


def test_unexpected_owner_callback_failure_is_reported_and_releases_budget():
    async def scenario():
        error = RuntimeError("injected owner failure")

        def receive(peer, message, size):
            raise error

        peer, budget, _, closed = make_peer(on_message=receive)
        peer.start()
        peer.reader.feed_data(encode_message(ping()))
        await until(lambda: peer.closed)
        await peer.close()
        assert peer.unexpected_error is error and closed == [peer]
        assert budget.frames == budget.bytes == 0
    asyncio.run(scenario())


def test_local_encoding_errors_do_not_masquerade_as_queue_overflow():
    async def scenario():
        peer, _, _, _ = make_peer(config=NodeConfig(max_frame_bytes=32))
        with pytest.raises(ProtocolError):
            peer.send(Message("NO_SUCH_MESSAGE", {}))
        with pytest.raises(PolicyLimitError):
            peer.send(ping())
        assert not peer.closed and peer.outbound_bytes == 0
        await peer.close()
    asyncio.run(scenario())


def test_real_loopback_tcp_fragmentation_and_coalescing():
    async def scenario():
        accepted = asyncio.get_running_loop().create_future()
        messages = []
        budget = Budget()

        def receive(peer, message, size):
            messages.append(message)
            return False

        def accept(reader, writer):
            peer = PeerConnection(
                reader, writer, config=NodeConfig(), on_message=receive,
                on_close=lambda peer: None, reserve=budget.reserve, release=budget.release,
            )
            peer.start()
            accepted.set_result(peer)

        server = await asyncio.start_server(accept, "127.0.0.1", 0, limit=4096)
        client = None
        peer = None
        try:
            _, client = await asyncio.wait_for(
                asyncio.open_connection(*server.sockets[0].getsockname()[:2]), 2
            )
            peer = await asyncio.wait_for(accepted, 2)
            frame = encode_message(ping(1))
            client.write(frame[:2])
            await client.drain()
            await asyncio.sleep(0)
            client.write(frame[2:9])
            await client.drain()
            await until(lambda: budget.frames == 1)
            client.write(frame[9:] + encode_message(ping(2)) + encode_message(ping(3)))
            await client.drain()
            await until(lambda: len(messages) == 3)
            assert messages == [ping(1), ping(2), ping(3)]
            assert budget.frames == budget.bytes == 0
        finally:
            server.close()
            if client is not None:
                client.close()
                await asyncio.wait_for(client.wait_closed(), 2)
            if peer is not None:
                await peer.close()
            await asyncio.wait_for(server.wait_closed(), 2)
    asyncio.run(scenario())


def test_candidates_are_bounded_deduplicated_and_expire_except_seeds():
    clock = Clock()
    seed = ("127.0.0.1", 5100)
    manager = PeerManager(NodeConfig(seeds=(seed,), max_candidates=3), clock=clock)
    assert manager.add_candidate(("127.0.0.1", 5101))
    assert manager.add_candidate(("127.0.0.1", 5102))
    assert not manager.add_candidate(("127.0.0.1", 5102))
    assert not manager.add_candidate(("127.0.0.1", 5103))
    assert len(manager.candidates) == 3
    assert manager.known_endpoints == []
    clock.now = 600
    assert manager.candidates == [seed]


def test_known_peers_require_successful_handshake_and_self_is_excluded():
    endpoint = ("127.0.0.1", 5100)
    manager = PeerManager(NodeConfig())
    assert manager.add_candidate(endpoint)
    assert manager.mark_attempt(endpoint)
    assert manager.due_candidates() == [] and manager.known_endpoints == []
    assert manager.mark_connected(endpoint)
    assert manager.known_endpoints == [endpoint] and manager.due_candidates() == []
    manager.mark_disconnected(endpoint)
    assert manager.known_endpoints == [endpoint]
    manager.set_self_endpoint(endpoint)
    assert manager.candidates == [] and manager.known_endpoints == []
    assert not manager.add_candidate(endpoint)
    assert not manager.mark_connected(endpoint)


@pytest.mark.parametrize("endpoint", [
    ("8.8.8.8", 5100), ("localhost", 5100), ("127.0.0.1", True),
    ("127.0.0.1", 0), ("127.0.0.1", 65536), ("169.254.0.1", 5100),
    ("224.0.0.1", 5100), ("192.168.1.5", 5100), ("127.0.0.1",),
])
def test_candidate_policy_rejects_forbidden_or_malformed_endpoints(endpoint):
    manager = PeerManager(NodeConfig())
    with pytest.raises(ValueError):
        manager.add_candidate(endpoint)
    assert not manager.candidates


def test_seed_backoff_is_exponential_capped_and_resets_after_connection():
    clock = Clock()
    seed = ("127.0.0.1", 5100)
    manager = PeerManager(NodeConfig(seeds=(seed,)), clock=clock, rng=NoJitter())
    for delay in (1, 2, 4, 8, 16, 30, 30):
        assert manager.due_candidates() == [seed]
        assert manager.mark_attempt(seed)
        assert not manager.mark_attempt(seed)
        manager.mark_disconnected(seed)
        assert not manager.due_candidates()
        clock.now += delay - 0.01
        assert not manager.due_candidates()
        clock.now += 0.01
    assert manager.mark_connected(seed)
    manager.mark_disconnected(seed)
    clock.now += 1
    assert manager.due_candidates() == [seed]


def test_discovered_retry_cycle_not_reset_by_duplicate_advertisement():
    clock = Clock()
    endpoint = ("127.0.0.1", 5100)
    manager = PeerManager(NodeConfig(), clock=clock, rng=NoJitter())
    manager.add_candidate(endpoint)
    for now in (0, 1, 3):
        clock.now = now
        assert manager.mark_attempt(endpoint)
        manager.mark_disconnected(endpoint)
        assert not manager.add_candidate(endpoint)
    clock.now = 299
    assert not manager.due_candidates() and not manager.mark_attempt(endpoint)
    clock.now = 300
    assert manager.due_candidates() == [endpoint]
    assert manager.mark_attempt(endpoint)


def test_candidate_snapshots_are_detached_and_operator_seed_can_replace_hint():
    clock = Clock()
    first, second = ("127.0.0.1", 5100), ("127.0.0.1", 5101)
    manager = PeerManager(NodeConfig(max_candidates=1), clock=clock)
    manager.add_candidate(first)
    snapshot = manager.candidates
    snapshot.clear()
    assert manager.candidates == [first]
    assert manager.add_candidate(second, seed=True)
    assert manager.candidates == [second]
    assert not manager.add_candidate(first, seed=True)


def node_config(**changes):
    return NodeConfig(port=0, maintenance_interval=0.01, **changes)


def established(node):
    return [session for session in node._sessions.values()
            if session.peer.established and not session.peer.closed]


async def read_wire(reader):
    async def receive():
        prefix = await reader.readexactly(4)
        size = int.from_bytes(prefix, "big")
        assert 1 <= size <= NodeConfig().max_frame_bytes
        return decode_message(await reader.readexactly(size))
    return await asyncio.wait_for(receive(), 2)


async def read_type(reader, kind):
    for _ in range(16):
        message = await read_wire(reader)
        if message.type == kind:
            return message
    raise AssertionError(f"did not receive {kind}")


def version_payload(*, node_id="a" * 32, listen_port=5101):
    from blockchain.genesis import GENESIS_HASH
    from network.config import NETWORK_ID

    return {
        "network_id": NETWORK_ID, "genesis_hash": GENESIS_HASH,
        "node_id": node_id, "connection_nonce": "b" * 32,
        "listen_port": listen_port, "height": 0, "tip_hash": GENESIS_HASH,
    }


def unchecked_frame(message_type, payload, *, version=1):
    """Build deliberate wire violations without going through the local guard."""
    from crypto.hash import serialize

    body = serialize({"type": message_type, "payload": payload,
                      "request_id": None, "version": version})
    return len(body).to_bytes(4, "big") + body


async def raw_handshake(node):
    reader, writer = await asyncio.wait_for(asyncio.open_connection(*node.endpoint), 2)
    try:
        assert (await read_wire(reader)).type == "VERSION"
        payload = version_payload(listen_port=writer.get_extra_info("sockname")[1])
        writer.write(encode_message(Message("VERSION", payload))
                     + encode_message(Message("VERACK", {})))
        await writer.drain()
        assert (await read_type(reader, "VERACK")).payload == {}
        await until(lambda: bool(established(node)))
        return reader, writer, established(node)[0]
    except BaseException:
        writer.close()
        await asyncio.wait_for(writer.wait_closed(), 2)
        raise


async def close_raw(writer):
    if writer is not None:
        writer.close()
        try:
            await asyncio.wait_for(writer.wait_closed(), 2)
        except (OSError, TimeoutError):
            pass


def test_two_nodes_complete_handshake_and_advertise_only_verified_endpoints():
    from network.node import Node

    async def scenario():
        left, right = Node(node_config()), Node(node_config())
        try:
            await asyncio.gather(left.start(), right.start())
            peer = await asyncio.wait_for(left.connect(*right.endpoint), 2)
            await until(lambda: len(established(right)) == 1)
            assert peer.established and peer.node_id == right.node_id
            assert peer.outbound and not established(right)[0].peer.outbound
            assert established(left)[0].endpoint == right.endpoint
            assert established(right)[0].endpoint == left.endpoint
            assert left._manager.known_endpoints == [right.endpoint]
            assert right._manager.known_endpoints == [left.endpoint]
            assert (await left.get_status())["height"] == 0
        finally:
            await asyncio.wait_for(asyncio.gather(left.stop(), right.stop()), 3)
        assert left._inbound_events == left._inbound_bytes == 0
        assert right._inbound_events == right._inbound_bytes == 0
    asyncio.run(scenario())


@pytest.mark.parametrize("violation", [
    "wrong_network", "wrong_genesis", "wrong_version", "self_node_id",
    "wrong_genesis_tip", "repeat_version", "early_verack", "early_ping",
])
def test_handshake_violations_disconnect_offender_and_keep_node_running(violation):
    from network.node import Node

    async def scenario():
        node = Node(node_config())
        writer = None
        try:
            await node.start()
            reader, writer = await asyncio.wait_for(asyncio.open_connection(*node.endpoint), 2)
            assert (await read_wire(reader)).type == "VERSION"
            payload = version_payload()
            if violation == "wrong_network":
                payload["network_id"] = "another-network"
            elif violation == "wrong_genesis":
                payload["genesis_hash"] = "0" * 64
            elif violation == "self_node_id":
                payload["node_id"] = node.node_id
            elif violation == "wrong_genesis_tip":
                payload["tip_hash"] = "0" * 64
            frame = unchecked_frame("VERSION", payload, version=2 if violation == "wrong_version" else 1)
            if violation == "repeat_version":
                frame += frame
            elif violation == "early_verack":
                frame = encode_message(Message("VERACK", {}))
            elif violation == "early_ping":
                frame = encode_message(ping())
            writer.write(frame)
            await writer.drain()
            # VERSION or VERACK already buffered before rejection may precede EOF.
            await asyncio.wait_for(reader.read(), 2)
            await until(lambda: not node._sessions)
            assert node.state == "RUNNING" and not node._manager.known_endpoints
            assert (await node.get_status())["height"] == 0
        finally:
            await close_raw(writer)
            await asyncio.wait_for(node.stop(), 3)
        assert node._inbound_events == node._inbound_bytes == 0
    asyncio.run(scenario())


@pytest.mark.parametrize("kind", ["VERSION", "VERACK"])
def test_repeated_handshake_after_establishment_is_rejected(kind):
    from network.node import Node

    async def scenario():
        node = Node(node_config())
        writer = None
        try:
            await node.start()
            reader, writer, session = await raw_handshake(node)
            writer.write(encode_message(Message(kind, version_payload() if kind == "VERSION" else {})))
            await writer.drain()
            await asyncio.wait_for(reader.read(), 2)
            await until(lambda: session.peer.closed)
            assert node.state == "RUNNING"
        finally:
            await close_raw(writer)
            await asyncio.wait_for(node.stop(), 3)
    asyncio.run(scenario())


def test_public_self_connect_rejected_without_opening_socket():
    from network.node import Node

    async def scenario():
        node = Node(node_config())
        try:
            await node.start()
            with pytest.raises(PeerDisconnectedError):
                await node.connect(*node.endpoint)
            assert not node._sessions and not node._dial_tasks
        finally:
            await node.stop()
    asyncio.run(scenario())


def test_concurrent_calls_to_same_endpoint_share_one_dial_and_connection():
    from network.node import Node

    async def scenario():
        left, right = Node(node_config(max_concurrent_dials=1)), Node(node_config())
        try:
            await asyncio.gather(left.start(), right.start())
            peers = await asyncio.wait_for(asyncio.gather(
                *(left.connect(*right.endpoint) for _ in range(10))
            ), 2)
            assert all(peer is peers[0] for peer in peers)
            await until(lambda: len(established(right)) == 1)
            assert len(left._sessions) == len(right._sessions) == 1
        finally:
            await asyncio.wait_for(asyncio.gather(left.stop(), right.stop()), 3)
    asyncio.run(scenario())


def test_simultaneous_dials_choose_same_lower_id_initiator():
    from network.node import Node

    async def scenario():
        left, right = Node(node_config()), Node(node_config())
        left.node_id, right.node_id = "1" * 32, "2" * 32
        try:
            await asyncio.gather(left.start(), right.start())
            results = await asyncio.wait_for(asyncio.gather(
                left.connect(*right.endpoint), right.connect(*left.endpoint),
                return_exceptions=True,
            ), 2)
            await until(lambda: len(left._sessions) == len(right._sessions) == 1)
            assert len(established(left)) == len(established(right)) == 1
            assert established(left)[0].peer.outbound
            assert not established(right)[0].peer.outbound
            assert all(not isinstance(result, BaseException) for result in results), results
        finally:
            await asyncio.wait_for(asyncio.gather(left.stop(), right.stop()), 3)
    asyncio.run(scenario())


def test_half_open_peer_counts_against_slots_until_handshake_timeout():
    from network.node import Node

    async def scenario():
        node = Node(node_config(max_peers=1, handshake_timeout=0.08))
        first_writer = second_writer = None
        try:
            await node.start()
            first_reader, first_writer = await asyncio.wait_for(asyncio.open_connection(*node.endpoint), 2)
            assert (await read_wire(first_reader)).type == "VERSION"
            assert len(node._sessions) == 1 and not established(node)
            second_reader, second_writer = await asyncio.wait_for(asyncio.open_connection(*node.endpoint), 2)
            assert await asyncio.wait_for(second_reader.read(), 2) == b""
            assert len(node._sessions) == 1
            assert await asyncio.wait_for(first_reader.read(), 2) == b""
            await until(lambda: not node._sessions)
            assert node.state == "RUNNING"
        finally:
            await close_raw(first_writer)
            await close_raw(second_writer)
            await asyncio.wait_for(node.stop(), 3)
    asyncio.run(scenario())


def test_half_open_outbound_connection_consumes_dial_and_peer_slots():
    from network.node import Node

    async def scenario():
        writers = []

        def silent(reader, writer):
            writers.append(writer)

        server = await asyncio.start_server(silent, "127.0.0.1", 0)
        node = Node(node_config(max_peers=1, handshake_timeout=0.1))
        task = None
        try:
            await node.start()
            endpoint = server.sockets[0].getsockname()[:2]
            task = asyncio.create_task(node.connect(*endpoint))
            await until(lambda: bool(node._sessions))
            with pytest.raises(NodeBusyError):
                await node.connect("127.0.0.1", node.endpoint[1] + (1 if node.endpoint[1] < 65535 else -1))
            with pytest.raises((TimeoutError, PeerDisconnectedError)):
                await asyncio.wait_for(task, 2)
            await until(lambda: not node._sessions)
            assert node.state == "RUNNING"
        finally:
            if task is not None:
                await asyncio.gather(task, return_exceptions=True)
            server.close()
            for writer in writers:
                await close_raw(writer)
            await asyncio.wait_for(node.stop(), 3)
            await asyncio.wait_for(server.wait_closed(), 2)
    asyncio.run(scenario())


def test_ping_is_echoed_and_unsolicited_pong_disconnects():
    from network.node import Node

    async def scenario():
        node = Node(node_config())
        writer = None
        try:
            await node.start()
            reader, writer, session = await raw_handshake(node)
            writer.write(encode_message(ping(42)))
            await writer.drain()
            response = await read_type(reader, "PONG")
            assert response.payload == ping(42).payload
            writer.write(encode_message(Message("PONG", {"nonce": "f" * 32})))
            await writer.drain()
            await asyncio.wait_for(reader.read(), 2)
            await until(lambda: session.peer.closed)
            assert node.state == "RUNNING"
        finally:
            await close_raw(writer)
            await asyncio.wait_for(node.stop(), 3)
    asyncio.run(scenario())


@pytest.mark.parametrize("answer", ["correct", "wrong", "silent"])
def test_heartbeat_requires_matching_pong_before_deadline(answer):
    from network.node import Node

    async def scenario():
        node = Node(node_config(ping_interval=0.08, pong_timeout=0.05))
        writer = None
        try:
            await node.start()
            reader, writer, session = await raw_handshake(node)
            request = await read_type(reader, "PING")
            if answer != "silent":
                nonce = request.payload["nonce"] if answer == "correct" else "f" * 32
                writer.write(encode_message(Message("PONG", {"nonce": nonce})))
                await writer.drain()
            if answer == "correct":
                await until(lambda: session.ping_nonce is None)
                assert session.peer.established and not session.peer.closed
            else:
                await asyncio.wait_for(reader.read(), 2)
                await until(lambda: session.peer.closed)
            assert node.state == "RUNNING"
        finally:
            await close_raw(writer)
            await asyncio.wait_for(node.stop(), 3)
    asyncio.run(scenario())


def test_cancelling_one_connect_caller_preserves_shared_handshake():
    from network.node import Node

    async def scenario():
        allow_ack = asyncio.Event()
        connected = asyncio.Event()
        handlers = []

        async def remote(reader, writer):
            try:
                assert (await read_wire(reader)).type == "VERSION"
                payload = version_payload(listen_port=writer.get_extra_info("sockname")[1])
                writer.write(encode_message(Message("VERSION", payload)))
                await writer.drain()
                connected.set()
                await allow_ack.wait()
                writer.write(encode_message(Message("VERACK", {})))
                await writer.drain()
                await reader.read()
            finally:
                await close_raw(writer)

        def accept(reader, writer):
            handlers.append(asyncio.create_task(remote(reader, writer)))

        server = await asyncio.start_server(accept, "127.0.0.1", 0)
        node = Node(node_config())
        first = second = None
        try:
            await node.start()
            endpoint = server.sockets[0].getsockname()[:2]
            first = asyncio.create_task(node.connect(*endpoint))
            await asyncio.wait_for(connected.wait(), 2)
            second = asyncio.create_task(node.connect(*endpoint))
            first.cancel()
            with pytest.raises(asyncio.CancelledError):
                await first
            allow_ack.set()
            peer = await asyncio.wait_for(second, 2)
            assert peer.established and len(node._sessions) == 1
        finally:
            allow_ack.set()
            server.close()
            await asyncio.wait_for(node.stop(), 3)
            if first is not None:
                await asyncio.gather(first, return_exceptions=True)
            if second is not None:
                await asyncio.gather(second, return_exceptions=True)
            if handlers:
                await asyncio.wait_for(asyncio.gather(*handlers), 2)
            await asyncio.wait_for(server.wait_closed(), 2)
    asyncio.run(scenario())


def test_node_stop_survives_caller_cancellation_and_releases_listener_port():
    from network.node import Node

    async def scenario():
        left, right = Node(node_config()), Node(node_config())
        release_close = asyncio.Event()
        close_started = asyncio.Event()
        first = second = None
        rebound = None
        try:
            await asyncio.gather(left.start(), right.start())
            peer = await asyncio.wait_for(left.connect(*right.endpoint), 2)
            endpoint = left.endpoint
            original_close = peer.close

            async def delayed_close():
                close_started.set()
                await release_close.wait()
                await original_close()

            peer.close = delayed_close
            first = asyncio.create_task(left.stop())
            await asyncio.wait_for(close_started.wait(), 2)
            second = asyncio.create_task(left.stop())
            first.cancel()
            with pytest.raises(asyncio.CancelledError):
                await first
            assert left.state == "STOPPING"
            release_close.set()
            await asyncio.wait_for(second, 3)
            assert left.state == "STOPPED"
            assert left._inbound_bytes == left._inbound_events == 0
            assert not left._sessions and not left._dial_tasks
            assert left._dispatcher_task.done() and left._maintenance_task.done()
            rebound = await asyncio.start_server(lambda reader, writer: writer.close(), *endpoint)
        finally:
            release_close.set()
            if rebound is not None:
                rebound.close()
                await asyncio.wait_for(rebound.wait_closed(), 2)
            await asyncio.wait_for(asyncio.gather(left.stop(), right.stop()), 3)
            if first is not None:
                await asyncio.gather(first, return_exceptions=True)
            if second is not None:
                await asyncio.gather(second, return_exceptions=True)
    asyncio.run(scenario())


@pytest.mark.parametrize("cancel_start_caller", [False, True])
def test_startup_race_cannot_reopen_listener_or_database_after_stop(
    monkeypatch, tmp_path, cancel_start_caller,
):
    from blockchain.blockchain import Blockchain
    from network.node import Node
    from storage.errors import StorageClosedError

    async def scenario():
        entered = asyncio.Event()
        never = asyncio.Event()
        original_start_server = asyncio.start_server
        allocated = []

        async def racing_server(*args, **kwargs):
            entered.set()
            try:
                await never.wait()
            except asyncio.CancelledError:
                # Emulate bind completing just as cancellation is delivered;
                # a returned server must still be recognized and closed.
                server = await original_start_server(*args, **kwargs)
                allocated.append((server, server.sockets[0].getsockname()[:2]))
                return server
            raise AssertionError("startup gate must be cancelled")

        monkeypatch.setattr(asyncio, "start_server", racing_server)
        db_path = tmp_path / "interrupted-start.sqlite3"
        node = Node(node_config(db_path=db_path))
        startup = asyncio.create_task(node.start())
        reopened = rebound = None
        try:
            await asyncio.wait_for(entered.wait(), 2)
            assert node.state == "STARTING" and db_path.exists()
            if cancel_start_caller:
                startup.cancel()
                with pytest.raises(asyncio.CancelledError):
                    await asyncio.wait_for(startup, 3)
                assert node.state == "FAILED"
            else:
                await asyncio.wait_for(node.stop(), 3)
                with pytest.raises((asyncio.CancelledError, NodeClosedError)):
                    await asyncio.wait_for(startup, 3)
                assert node.state == "STOPPED"
            assert node._start_task.done() and node._cleanup_task.done()
            assert not node._sessions and not node._dial_tasks
            assert node._dispatcher_task is None and node._maintenance_task is None
            assert len(allocated) == 1
            server, endpoint = allocated[0]
            assert not server.is_serving() and not server.sockets
            with pytest.raises(StorageClosedError):
                node._chain.get_mempool_stats()
            reopened = Blockchain(db_path=db_path)
            assert reopened.height == 0
            rebound = await original_start_server(lambda reader, writer: writer.close(), *endpoint)
        finally:
            await asyncio.wait_for(node.stop(), 3)
            await asyncio.gather(startup, return_exceptions=True)
            if rebound is not None:
                rebound.close()
                await asyncio.wait_for(rebound.wait_closed(), 2)
            if reopened is not None:
                reopened.close()
            for server, _ in allocated:
                server.close()
                await asyncio.wait_for(server.wait_closed(), 2)
    asyncio.run(scenario())


def test_outbound_handshake_and_its_dial_task_occupy_one_peer_slot():
    from network.node import Node

    async def scenario():
        remote_writers = []
        server = await asyncio.start_server(
            lambda reader, writer: remote_writers.append(writer), "127.0.0.1", 0
        )
        node = Node(node_config(max_peers=2, handshake_timeout=2))
        inbound_writer = dial = None
        try:
            await node.start()
            dial = asyncio.create_task(node.connect(*server.sockets[0].getsockname()[:2]))
            await until(lambda: len(node._sessions) == 1)
            assert len(node._dial_tasks) == 1
            assert node._occupied_slots() == 1
            inbound_reader, inbound_writer = await asyncio.wait_for(asyncio.open_connection(*node.endpoint), 2)
            assert (await read_wire(inbound_reader)).type == "VERSION"
            assert len(node._sessions) == 2 and node._occupied_slots() == 2
        finally:
            server.close()
            await close_raw(inbound_writer)
            await asyncio.wait_for(node.stop(), 3)
            if dial is not None:
                await asyncio.gather(dial, return_exceptions=True)
            for writer in remote_writers:
                await close_raw(writer)
            await asyncio.wait_for(server.wait_closed(), 2)
    asyncio.run(scenario())


def test_outbound_peer_cannot_change_its_dial_endpoint_in_version():
    from network.node import Node

    async def scenario():
        handlers = []

        async def dishonest(reader, writer):
            try:
                await read_wire(reader)
                port = writer.get_extra_info("sockname")[1]
                port = port + 1 if port < 65535 else port - 1
                payload = version_payload(listen_port=port)
                writer.write(encode_message(Message("VERSION", payload))
                             + encode_message(Message("VERACK", {})))
                await writer.drain()
                await reader.read()
            finally:
                await close_raw(writer)

        def accept(reader, writer):
            handlers.append(asyncio.create_task(dishonest(reader, writer)))

        server = await asyncio.start_server(accept, "127.0.0.1", 0)
        node = Node(node_config())
        try:
            await node.start()
            endpoint = server.sockets[0].getsockname()[:2]
            with pytest.raises(PeerDisconnectedError):
                await asyncio.wait_for(node.connect(*endpoint), 2)
            await until(lambda: not node._sessions)
            assert node.state == "RUNNING" and node._manager.known_endpoints == []
        finally:
            server.close()
            await asyncio.wait_for(node.stop(), 3)
            if handlers:
                await asyncio.wait_for(asyncio.gather(*handlers), 2)
            await asyncio.wait_for(server.wait_closed(), 2)
    asyncio.run(scenario())
