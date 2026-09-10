"""Exact protocol-v1 message schemas; ledger contents stay opaque here."""

from dataclasses import dataclass
import re

from network.config import (
    MAX_BLOCK_BATCH, MAX_HEIGHT, MAX_MEMPOOL_PAGE, MAX_PEER_ENDPOINTS,
    NETWORK_ID, PROTOCOL_VERSION, local_ipv4,
)
from network.errors import ProtocolError


ERROR_CODES = frozenset({
    "BAD_MESSAGE", "UNSUPPORTED_VERSION", "WRONG_NETWORK", "UNKNOWN_ANCHOR",
    "FORK_UNSUPPORTED", "STALE_TIP", "SNAPSHOT_EXPIRED", "POLICY_LIMIT", "BUSY",
})
REQUEST_TYPES = frozenset({"GET_STATUS", "GET_PEERS", "GET_BLOCKS", "GET_MEMPOOL"})
RESPONSE_TYPES = frozenset({"STATUS", "PEERS", "BLOCKS", "MEMPOOL", "ERROR"})
REQUEST_RESPONSES = {
    "GET_STATUS": "STATUS", "GET_PEERS": "PEERS", "GET_BLOCKS": "BLOCKS",
    "GET_MEMPOOL": "MEMPOOL",
}
_SCHEMAS = {
    "VERSION": {"network_id", "genesis_hash", "node_id", "connection_nonce", "listen_port", "height", "tip_hash"},
    "VERACK": set(), "GET_STATUS": set(), "STATUS": {"height", "tip_hash"},
    "GET_PEERS": set(), "PEERS": {"peers"}, "NEW_TRANSACTION": {"transaction"},
    "NEW_BLOCK": {"block"}, "GET_BLOCKS": {"anchor_height", "anchor_hash", "limit"},
    "BLOCKS": {"anchor_height", "anchor_hash", "tip_height", "tip_hash", "blocks", "more"},
    "GET_MEMPOOL": {"tip_hash", "snapshot_id", "cursor", "limit"},
    "MEMPOOL": {"tip_hash", "snapshot_id", "cursor", "transactions", "next_cursor", "done"},
    "PING": {"nonce"}, "PONG": {"nonce"}, "ERROR": {"code", "message"},
}
MESSAGE_TYPES = frozenset(_SCHEMAS)
_HASH = re.compile(r"[0-9a-f]{64}\Z")
_TOKEN = re.compile(r"[0-9a-f]{32}\Z")


@dataclass(frozen=True)
class Message:
    type: str
    payload: dict
    request_id: str | None = None
    version: int = PROTOCOL_VERSION


def _require(condition: bool, reason: str) -> None:
    if not condition:
        raise ProtocolError(reason)


def _integer(value: object, name: str, minimum: int = 0, maximum: int = MAX_HEIGHT) -> None:
    _require(type(value) is int and minimum <= value <= maximum, f"invalid {name}")


def _hex(value: object, name: str, token: bool = False) -> None:
    pattern = _TOKEN if token else _HASH
    _require(type(value) is str and pattern.fullmatch(value) is not None, f"invalid {name}")


def _item(value: object) -> None:
    # Full base64/canonical codec validation happens on the blockchain owner.
    _require(type(value) is str and bool(value) and value.isascii(), "signed item must be an ASCII base64 string")


def validate_message(message: Message) -> None:
    _require(isinstance(message, Message), "expected a Message")
    _require(type(message.version) is int and message.version == PROTOCOL_VERSION, "unsupported protocol version")
    _require(type(message.type) is str and message.type in MESSAGE_TYPES, "unknown message type")
    payload = message.payload
    _require(type(payload) is dict and set(payload) == _SCHEMAS[message.type], "payload has missing or unexpected fields")
    required_id = message.type in REQUEST_TYPES or message.type in {"PEERS", "BLOCKS", "MEMPOOL"}
    optional_id = message.type in {"STATUS", "ERROR"}
    if required_id or (optional_id and message.request_id is not None):
        _hex(message.request_id, "request_id", token=True)
    else:
        _require(message.request_id is None, "control/announcement request_id must be null")

    for name in ("height", "anchor_height", "tip_height", "cursor", "next_cursor"):
        if name in payload:
            _integer(payload[name], name)
    for name in ("genesis_hash", "tip_hash", "anchor_hash"):
        if name in payload:
            _hex(payload[name], name)
    for name in ("node_id", "connection_nonce", "nonce"):
        if name in payload:
            _hex(payload[name], name, token=True)
    for name in ("more", "done"):
        if name in payload:
            _require(type(payload[name]) is bool, f"{name} must be boolean")
    for name in ("transaction", "block"):
        if name in payload:
            _item(payload[name])

    if message.type == "VERSION":
        _require(type(payload["network_id"]) is str and payload["network_id"] == NETWORK_ID, "wrong network")
        _integer(payload["listen_port"], "listen_port", 1, 65535)
    elif message.type == "GET_BLOCKS":
        _integer(payload["limit"], "limit", 1, MAX_BLOCK_BATCH)
    elif message.type == "BLOCKS":
        _require(type(payload["blocks"]) is list and len(payload["blocks"]) <= MAX_BLOCK_BATCH, "invalid block batch")
        for block in payload["blocks"]:
            _item(block)
    elif message.type == "GET_MEMPOOL":
        _integer(payload["limit"], "limit", 1, MAX_MEMPOOL_PAGE)
        if payload["snapshot_id"] is None:
            _require(payload["cursor"] == 0, "first snapshot request must start at cursor zero")
        else:
            _hex(payload["snapshot_id"], "snapshot_id", token=True)
    elif message.type == "MEMPOOL":
        _hex(payload["snapshot_id"], "snapshot_id", token=True)
        _require(type(payload["transactions"]) is list and len(payload["transactions"]) <= MAX_MEMPOOL_PAGE, "invalid mempool page")
        for transaction in payload["transactions"]:
            _item(transaction)
        _require(payload["next_cursor"] == payload["cursor"] + len(payload["transactions"]), "noncontiguous mempool cursor")
        _require(payload["done"] or bool(payload["transactions"]), "unfinished mempool page must progress")
    elif message.type == "PEERS":
        _require(type(payload["peers"]) is list and len(payload["peers"]) <= MAX_PEER_ENDPOINTS, "invalid peers list")
        for endpoint in payload["peers"]:
            _require(type(endpoint) is dict and set(endpoint) == {"host", "port"}, "invalid peer endpoint fields")
            try:
                local_ipv4(endpoint["host"])
            except ValueError as error:
                raise ProtocolError("invalid peer IPv4 address") from error
            _integer(endpoint["port"], "peer port", 1, 65535)
    elif message.type == "ERROR":
        _require(type(payload["code"]) is str and payload["code"] in ERROR_CODES, "unknown error code")
        _require(type(payload["message"]) is str and len(payload["message"]) <= 256, "error message exceeds 256 characters")
