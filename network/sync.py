"""Bounded, anchored full-block and parent-first pending synchronization.

All methods are synchronous and called exclusively by the Node dispatcher.
This module never replaces a chain, opens a database, or trusts peer state.
"""

from dataclasses import dataclass
import base64
import secrets

from network.errors import PolicyLimitError, ProtocolError
from network.messages import Message
from network.protocol import (
    encode_message, pack_block, pack_transaction, unpack_block,
    unpack_transaction,
)


def raw_size(encoded: str) -> int:
    return len(encoded) // 4 * 3 - (len(encoded) - len(encoded.rstrip("=")))


@dataclass
class ExportSnapshot:
    token: str
    tip: str
    items: list[bytes]
    size: int
    cursor: int
    created: float
    touched: float


@dataclass
class PendingDownload:
    tip: str
    token: str | None = None
    cursor: int = 0
    size: int = 0
    count: int = 0


class SyncManager:
    def __init__(self, node):
        self.node = node
        self.config = node.config
        self.exports: dict[str, ExportSnapshot] = {}
        self.downloads: dict[str, PendingDownload] = {}
        self.snapshot_bytes = 0
        self.source: str | None = None

    def _drop_export(self, connection_id):
        snapshot = self.exports.pop(connection_id, None)
        if snapshot is not None:
            self.snapshot_bytes -= snapshot.size

    def disconnected(self, connection_id):
        self._drop_export(connection_id)
        self.downloads.pop(connection_id, None)
        if self.source == connection_id:
            self.source = None

    def clear(self):
        self.exports.clear()
        self.downloads.clear()
        self.snapshot_bytes = 0
        self.source = None

    def tip_changed(self):
        # Responses to old requests still get correlated, then discarded as
        # stale; never mistake a legitimate race for a malformed remote ledger.
        for connection_id in list(self.exports):
            self._drop_export(connection_id)
        self.downloads.clear()
        for session in self.node._sessions.values():
            session.next_mempool = 0.0

    def tick(self, now):
        for connection_id, snapshot in list(self.exports.items()):
            if (now - snapshot.touched >= self.config.snapshot_idle_timeout
                    or now - snapshot.created >= self.config.snapshot_lifetime):
                self._drop_export(connection_id)
        height, tip = self.node._tip()
        sessions = [s for s in self.node._sessions.values()
                    if s.peer.established and not s.peer.closed]
        if self.source is not None and not any(
                s.peer.connection_id == self.source for s in sessions):
            self.source = None
        if self.source is None:
            candidates = [s for s in sessions
                          if s.remote_height > height and now >= s.sync_after
                          and s.sync_state != "DIVERGED"
                          and not self.node._has_request(s, "GET_BLOCKS")]
            if candidates:
                session = min(candidates, key=lambda s: (-s.remote_height, s.peer.node_id))
                request = self.node._request(session, "GET_BLOCKS", {
                    "anchor_height": height, "anchor_hash": tip,
                    "limit": self.config.block_batch_size,
                })
                if request is not None:
                    self.source = session.peer.connection_id
                    session.sync_state = "BLOCK_SYNC"
        for session in sessions:
            if session.remote_height == height and session.remote_tip != tip:
                session.sync_state = "DIVERGED"
                session.error = "FORK_UNSUPPORTED"
            if (session.remote_height == height and session.remote_tip == tip
                    and session.sync_state != "DIVERGED"
                    and now >= session.next_mempool
                    and not self.node._has_request(session, "GET_MEMPOOL")):
                download = self.downloads.get(session.peer.connection_id)
                if download is None:
                    download = PendingDownload(tip)
                request = self.node._request(session, "GET_MEMPOOL", {
                    "tip_hash": download.tip, "snapshot_id": download.token,
                    "cursor": download.cursor, "limit": self.config.mempool_page_size,
                })
                if request is not None:
                    self.downloads[session.peer.connection_id] = download
                    session.sync_state = "MEMPOOL_SYNC"

    def failed_request(self, session, request, code):
        now = self.node._clock()
        session.error = code
        if request.kind == "GET_BLOCKS":
            self.source = None
            session.sync_after = now + self.config.retry_delay
            session.sync_state = "IDLE"
            if code == "FORK_UNSUPPORTED":
                session.sync_state = "DIVERGED"
            if code == "UNKNOWN_ANCHOR":
                session.rejected_anchor = (request.payload["anchor_height"],
                                           request.payload["anchor_hash"])
                self.node._request(session, "GET_STATUS", {})
        elif request.kind == "GET_MEMPOOL":
            self.downloads.pop(session.peer.connection_id, None)
            session.next_mempool = now + self.config.retry_delay
            session.sync_state = "IDLE"
            if code == "STALE_TIP":
                self.node._request(session, "GET_STATUS", {})

    def serve_blocks(self, session, message):
        payload = message.payload
        chain = self.node._chain
        anchor = chain.get_block_by_height(payload["anchor_height"])
        if anchor is None or anchor.hash() != payload["anchor_hash"]:
            self.node._error(session, message.request_id, "UNKNOWN_ANCHOR")
            return
        height, tip = self.node._tip()
        result = {
            "anchor_height": payload["anchor_height"],
            "anchor_hash": payload["anchor_hash"],
            "tip_height": height, "tip_hash": tip, "blocks": [], "more": False,
        }
        for index in range(payload["anchor_height"] + 1,
                           min(height, payload["anchor_height"] + payload["limit"]) + 1):
            try:
                encoded = pack_block(chain.get_block_by_height(index),
                                     max_item_bytes=self.config.max_item_bytes)
                trial = dict(result, blocks=[*result["blocks"], encoded], more=index < height)
                encode_message(Message("BLOCKS", trial, message.request_id),
                               max_frame_bytes=self.config.max_frame_bytes)
            except PolicyLimitError:
                if not result["blocks"]:
                    self.node._error(session, message.request_id, "POLICY_LIMIT")
                    return
                break
            result = trial
        result["more"] = payload["anchor_height"] + len(result["blocks"]) < height
        self.node._send(session, Message("BLOCKS", result, message.request_id))

    def receive_blocks(self, session, request, message):
        self.source = None
        session.sync_state = "IDLE"
        expected, payload = request.payload, message.payload
        if (payload["anchor_height"] != expected["anchor_height"]
                or payload["anchor_hash"] != expected["anchor_hash"]):
            raise ProtocolError("BLOCKS does not echo the requested anchor")
        height, tip = self.node._tip()
        if (height, tip) != (expected["anchor_height"], expected["anchor_hash"]):
            return
        items = payload["blocks"]
        end_height = height + len(items)
        if (len(items) > expected["limit"] or end_height > payload["tip_height"]
                or payload["tip_height"] < height
                or payload["more"] != (end_height < payload["tip_height"])
                or (payload["more"] and not items)):
            raise ProtocolError("BLOCKS metadata is inconsistent or makes no progress")
        for encoded in items:
            block = unpack_block(encoded, max_item_bytes=self.config.max_item_bytes)
            if block.previous_block_hash != self.node._tip()[1]:
                raise ProtocolError("BLOCKS does not extend the accepted prefix")
            if not self.node._accept_block(block, source=session):
                self.failed_request(session, request, "BAD_MESSAGE")
                return
        if not payload["more"] and self.node._tip()[1] != payload["tip_hash"]:
            raise ProtocolError("BLOCKS final hash differs from advertised snapshot")
        session.remote_height, session.remote_tip = payload["tip_height"], payload["tip_hash"]
        if not items:
            # A high advertised tip is not progress. Avoid repeatedly selecting
            # a peer that alternates inflated STATUS with empty anchored replies.
            session.sync_after = self.node._clock() + self.config.retry_delay
            session.error = "NO_PROGRESS"
        else:
            session.sync_after = 0.0
            session.error = None
        if not payload["more"]:
            self.node._request(session, "GET_STATUS", {})

    def serve_mempool(self, session, message):
        now = self.node._clock()
        connection_id = session.peer.connection_id
        payload = message.payload
        tip = self.node._tip()[1]
        if payload["tip_hash"] != tip:
            self._drop_export(connection_id)
            self.node._error(session, message.request_id, "STALE_TIP")
            return
        snapshot = self.exports.get(connection_id)
        if snapshot is not None and (
                now - snapshot.touched >= self.config.snapshot_idle_timeout
                or now - snapshot.created >= self.config.snapshot_lifetime):
            self._drop_export(connection_id)
            snapshot = None
        if payload["snapshot_id"] is None:
            if snapshot is not None or now < session.next_export:
                self.node._error(session, message.request_id, "BUSY")
                return
            session.next_export = now + self.config.snapshot_cooldown
            count, size = self.node._chain.get_mempool_stats()
            if (count > self.config.snapshot_max_transactions
                    or size > self.config.snapshot_max_bytes):
                self.node._error(session, message.request_id, "POLICY_LIMIT")
                return
            if self.snapshot_bytes + size > self.config.snapshot_global_bytes:
                self.node._error(session, message.request_id, "BUSY")
                return
            self.snapshot_bytes += size
            try:
                token = secrets.token_hex(16)
                items = []
                for tx in self.node._chain.mempool.get_transactions():
                    encoded = pack_transaction(tx, max_item_bytes=self.config.max_item_bytes)
                    # Every item must fit even at the largest possible cursor.
                    probe = {"tip_hash": tip, "snapshot_id": token, "cursor": count,
                             "transactions": [encoded], "next_cursor": count + 1, "done": False}
                    encode_message(Message("MEMPOOL", probe, message.request_id),
                                   max_frame_bytes=self.config.max_frame_bytes)
                    # Retain raw signed bytes, not the 4/3 larger base64 string,
                    # so the global byte reservation measures retained payloads.
                    items.append(base64.b64decode(encoded, validate=True))
                snapshot = ExportSnapshot(token, tip, items, size, 0, now, now)
                self.exports[connection_id] = snapshot
            except BaseException as error:
                self.snapshot_bytes -= size
                if isinstance(error, PolicyLimitError):
                    self.node._error(session, message.request_id, "POLICY_LIMIT")
                    return
                raise
        elif (snapshot is None or snapshot.token != payload["snapshot_id"]):
            self.node._error(session, message.request_id, "SNAPSHOT_EXPIRED")
            return
        if payload["cursor"] != snapshot.cursor:
            raise ProtocolError("GET_MEMPOOL cursor is not the next snapshot page")
        start = snapshot.cursor
        result = {"tip_hash": tip, "snapshot_id": snapshot.token, "cursor": start,
                  "transactions": [], "next_cursor": start, "done": start == len(snapshot.items)}
        for index in range(start, min(len(snapshot.items), start + payload["limit"])):
            encoded = base64.b64encode(snapshot.items[index]).decode("ascii")
            trial = dict(result, transactions=[*result["transactions"], encoded],
                         next_cursor=index + 1, done=index + 1 == len(snapshot.items))
            try:
                encode_message(Message("MEMPOOL", trial, message.request_id),
                               max_frame_bytes=self.config.max_frame_bytes)
            except PolicyLimitError:
                break
            result = trial
        if not result["transactions"] and not result["done"]:
            self._drop_export(connection_id)
            self.node._error(session, message.request_id, "POLICY_LIMIT")
            return
        snapshot.cursor = result["next_cursor"]
        snapshot.touched = now
        self.node._send(session, Message("MEMPOOL", result, message.request_id))
        if result["done"]:
            self._drop_export(connection_id)

    def receive_mempool(self, session, request, message):
        connection_id, payload = session.peer.connection_id, message.payload
        download = self.downloads.get(connection_id)
        if self.node._tip()[1] != request.payload["tip_hash"] or download is None:
            return
        if (payload["tip_hash"] != download.tip
                or payload["cursor"] != download.cursor
                or (download.token is not None and payload["snapshot_id"] != download.token)):
            raise ProtocolError("MEMPOOL snapshot, tip or cursor mismatch")
        items = payload["transactions"]
        if (len(items) > request.payload["limit"]
                or payload["next_cursor"] != download.cursor + len(items)
                or (not items and not payload["done"])):
            raise ProtocolError("MEMPOOL pagination makes no progress")
        # Count and byte totals cover the entire snapshot, not just one frame.
        page_size = sum(raw_size(item) for item in items)
        if (download.count + len(items) > self.config.snapshot_max_transactions
                or download.size + page_size > self.config.snapshot_max_bytes):
            raise PolicyLimitError("Incoming pending snapshot exceeds node policy")
        for encoded in items:
            tx = unpack_transaction(encoded, max_item_bytes=self.config.max_item_bytes)
            self.node._submit_transaction(tx, source=session)
        download.token = payload["snapshot_id"]
        download.cursor = payload["next_cursor"]
        download.count += len(items)
        download.size += page_size
        session.error = None
        if payload["done"]:
            self.downloads.pop(connection_id, None)
            session.next_mempool = self.node._clock() + self.config.mempool_refresh_interval
            session.sync_state = "IDLE"
