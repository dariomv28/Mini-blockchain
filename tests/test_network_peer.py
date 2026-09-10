"""Transport bounds and candidate policy, using asyncio.run and loopback only."""

import asyncio
import pytest

from network.config import NodeConfig
from network.errors import PolicyLimitError, ProtocolError
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
