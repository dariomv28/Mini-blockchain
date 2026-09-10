"""Bounded TCP transport; ledger and handshake decisions belong to the owner."""

from __future__ import annotations

import asyncio
import logging
import secrets
import time
from collections.abc import Callable
from typing import Any

from .errors import ProtocolError
from .protocol import decode_message, encode_message


logger = logging.getLogger(__name__)


class TokenBucket:
    """A monotonic, bounded token bucket with an injectable clock."""

    def __init__(self, rate: float, capacity: float, *, clock=time.monotonic):
        if rate <= 0 or capacity <= 0:
            raise ValueError("token rate and capacity must be positive")
        self.rate = rate
        self.capacity = capacity
        self.tokens = float(capacity)
        self._clock = clock
        self._updated = clock()

    def consume(self, amount: float = 1) -> bool:
        if amount < 0:
            raise ValueError("token amount must be nonnegative")
        now = self._clock()
        elapsed = max(0.0, now - self._updated)
        self._updated = max(self._updated, now)
        self.tokens = min(self.capacity, self.tokens + elapsed * self.rate)
        if amount > self.tokens:
            return False
        self.tokens -= amount
        return True


class PeerConnection:
    """One FIFO writer and one framed reader on an owner event loop.

    ``reserve`` is called before reading a frame body, with the complete wire
    size (body plus the four-byte prefix). ``on_message`` is synchronous and
    returns True only when it takes ownership of that reservation. Otherwise
    the reader releases it, including on timeout, cancellation or exceptions.

    A send only enqueues; its frame/count budget remains reserved through drain.
    Closing is shared and shielded from cancellation by any individual caller.
    """

    def __init__(
        self,
        reader: asyncio.StreamReader,
        writer: asyncio.StreamWriter,
        *,
        config,
        on_message: Callable[["PeerConnection", Any, int], bool],
        on_close: Callable[["PeerConnection"], None],
        reserve: Callable[[int], bool],
        release: Callable[[int], None],
        clock=time.monotonic,
        outbound: bool = False,
    ):
        self.reader = reader
        self.writer = writer
        self.config = config
        self.connection_id = secrets.token_hex(16)
        self.connection_nonce = secrets.token_hex(16)
        self.remote_nonce: str | None = None
        self.node_id: str | None = None
        self.outbound = outbound
        remote = writer.get_extra_info("peername")
        self.endpoint = (remote[0], remote[1]) if remote else None
        self.established = False
        self.closed = False
        self.close_reason: str | None = None
        self.unexpected_error: Exception | None = None
        self._clock = clock
        self.last_received = self.last_sent = clock()
        self._on_message = on_message
        self._on_close = on_close
        self._reserve = reserve
        self._release = release
        self._outbound: asyncio.Queue[bytes] = asyncio.Queue(
            maxsize=config.outbound_max_frames
        )
        self._outbound_frames = 0
        self._outbound_bytes = 0
        self.reader_task: asyncio.Task | None = None
        self.writer_task: asyncio.Task | None = None
        self._close_task: asyncio.Task | None = None
        self._close_notified = False
        self._message_bucket = TokenBucket(
            config.message_rate, config.message_burst, clock=clock
        )
        self._byte_bucket = TokenBucket(config.byte_rate, config.byte_burst, clock=clock)

    @property
    def outbound_frames(self) -> int:
        """Frames queued or held by the writer awaiting drain."""
        return self._outbound_frames

    @property
    def outbound_bytes(self) -> int:
        """Complete wire bytes queued or held by the writer awaiting drain."""
        return self._outbound_bytes

    def start(self) -> None:
        if self.closed or self.reader_task is not None:
            return
        self.reader_task = asyncio.create_task(
            self._read_loop(), name=f"peer-reader-{self.connection_id}"
        )
        self.writer_task = asyncio.create_task(
            self._write_loop(), name=f"peer-writer-{self.connection_id}"
        )

    def send(self, message) -> bool:
        """Enqueue a complete encoded frame without waiting for a slow socket.

        Encoding failures propagate to the owner, which can distinguish local
        policy limits from programmer errors. Overflow disconnects this peer.
        """
        if self.closed:
            return False
        frame = encode_message(message, max_frame_bytes=self.config.max_frame_bytes)
        if (
            self._outbound_frames >= self.config.outbound_max_frames
            or self._outbound_bytes + len(frame) > self.config.outbound_max_bytes
        ):
            self.close_reason = "outbound queue limit"
            self._begin_close()
            return False
        self._outbound.put_nowait(frame)
        self._outbound_frames += 1
        self._outbound_bytes += len(frame)
        return True

    async def _read_loop(self) -> None:
        try:
            while not self.closed:
                prefix = await asyncio.wait_for(
                    self.reader.readexactly(4), timeout=self.config.read_timeout
                )
                body_size = int.from_bytes(prefix, "big")
                if not 1 <= body_size <= self.config.max_frame_bytes:
                    raise ProtocolError("frame length outside transport limits")
                wire_size = body_size + 4
                if not self._message_bucket.consume() or not self._byte_bucket.consume(
                    wire_size
                ):
                    raise ProtocolError("incoming rate limit")
                if not self._reserve(wire_size):
                    self.close_reason = "global inbound queue limit"
                    return
                owned_size = wire_size
                try:
                    body = await asyncio.wait_for(
                        self.reader.readexactly(body_size),
                        timeout=self.config.body_timeout,
                    )
                    message = decode_message(
                        body, max_frame_bytes=self.config.max_frame_bytes
                    )
                    self.last_received = self._clock()
                    if self._on_message(self, message, wire_size):
                        owned_size = 0
                finally:
                    if owned_size:
                        self._release(owned_size)
                # readexactly can complete synchronously for buffered frames.
                await asyncio.sleep(0)
        except asyncio.CancelledError:
            raise
        except (ProtocolError, asyncio.IncompleteReadError, OSError, TimeoutError) as exc:
            self.close_reason = self.close_reason or type(exc).__name__
        except Exception as exc:
            self.unexpected_error = exc
            self.close_reason = "unexpected reader error"
            logger.exception("peer reader failed connection=%s", self.connection_id)
        finally:
            self._begin_close()

    async def _write_loop(self) -> None:
        try:
            while not self.closed:
                frame = await self._outbound.get()
                try:
                    self.writer.write(frame)
                    await asyncio.wait_for(
                        self.writer.drain(), timeout=self.config.write_timeout
                    )
                    self.last_sent = self._clock()
                finally:
                    self._outbound_frames -= 1
                    self._outbound_bytes -= len(frame)
                    self._outbound.task_done()
                # drain can complete synchronously for a writable transport.
                await asyncio.sleep(0)
        except asyncio.CancelledError:
            raise
        except (OSError, TimeoutError) as exc:
            self.close_reason = self.close_reason or type(exc).__name__
        except Exception as exc:
            self.unexpected_error = exc
            self.close_reason = "unexpected writer error"
            logger.exception("peer writer failed connection=%s", self.connection_id)
        finally:
            self._begin_close()

    def _begin_close(self) -> asyncio.Task:
        if self._close_task is None:
            self.closed = True
            self.established = False
            self._close_task = asyncio.create_task(
                self._cleanup(), name=f"peer-close-{self.connection_id}"
            )
        return self._close_task

    async def close(self) -> None:
        await asyncio.shield(self._begin_close())

    async def _cleanup(self) -> None:
        try:
            self.writer.close()
        except OSError:
            pass
        except Exception as exc:
            self.unexpected_error = self.unexpected_error or exc
            logger.exception("peer socket close failed connection=%s", self.connection_id)
        try:
            tasks = [
                task
                for task in (self.reader_task, self.writer_task)
                if task is not None and task is not asyncio.current_task()
            ]
            for task in tasks:
                if not task.done():
                    task.cancel()
            if tasks:
                await asyncio.gather(*tasks, return_exceptions=True)
            while not self._outbound.empty():
                frame = self._outbound.get_nowait()
                self._outbound_frames -= 1
                self._outbound_bytes -= len(frame)
                self._outbound.task_done()
            try:
                await asyncio.wait_for(
                    self.writer.wait_closed(), timeout=self.config.close_timeout
                )
            except (OSError, TimeoutError):
                # Abort after the bounded graceful close deadline.
                transport = getattr(self.writer, "transport", None)
                if transport is not None:
                    transport.abort()
        finally:
            if not self._close_notified:
                self._close_notified = True
                self._on_close(self)
