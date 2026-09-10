"""Bounded canonical envelopes and adapters for Phase 8 signed codecs."""

import base64
import binascii
import json

from crypto.hash import serialize
from network.config import MAX_FRAME_BYTES, MAX_ITEM_BYTES
from network.errors import PolicyLimitError, ProtocolError
from network.messages import Message, validate_message
from storage.codec import decode_block, decode_transaction, encode_block, encode_transaction
from storage.errors import StorageCorruptionError


MAX_JSON_DEPTH = 32


def _limit(value: object, name: str) -> None:
    if type(value) is not int or value <= 0:
        raise ValueError(f"{name} must be a positive integer")


def _check_depth(data: bytes) -> None:
    """Scan containers before any recursive JSON decoding, honoring escapes."""
    depth = 0
    in_string = False
    escaped = False
    for byte in data:
        if in_string:
            if escaped:
                escaped = False
            elif byte == 92:
                escaped = True
            elif byte == 34:
                in_string = False
        elif byte == 34:
            in_string = True
        elif byte in (91, 123):
            depth += 1
            if depth > MAX_JSON_DEPTH:
                raise ProtocolError("JSON nesting exceeds protocol limit")
        elif byte in (93, 125):
            depth -= 1
            if depth < 0:
                raise ProtocolError("unbalanced JSON containers")
    if in_string or depth:
        raise ProtocolError("unterminated JSON string/container")


def _unique_object(pairs: list[tuple[str, object]]) -> dict:
    result = {}
    for key, value in pairs:
        if key in result:
            raise ProtocolError("duplicate JSON key")
        result[key] = value
    return result


def _reject_number(value: str) -> None:
    raise ProtocolError("floating-point/non-finite JSON numbers are unsupported")


def encode_message(message: Message, *, max_frame_bytes: int = MAX_FRAME_BYTES) -> bytes:
    """Return one complete 4-byte-length-prefixed canonical message frame."""
    _limit(max_frame_bytes, "max_frame_bytes")
    validate_message(message)
    try:
        body = serialize({
            "payload": message.payload, "request_id": message.request_id,
            "type": message.type, "version": message.version,
        })
    except (TypeError, ValueError, OverflowError, RecursionError) as error:
        raise ProtocolError("cannot encode envelope") from error
    if len(body) > min(max_frame_bytes, 2**32 - 1):
        raise PolicyLimitError("message exceeds frame byte limit")
    return len(body).to_bytes(4, "big") + body


def decode_message(body: bytes, *, max_frame_bytes: int = MAX_FRAME_BYTES) -> Message:
    """Decode a frame body; the transport reads/checks the prefix separately."""
    _limit(max_frame_bytes, "max_frame_bytes")
    if type(body) is not bytes or not body:
        raise ProtocolError("frame body must be nonempty bytes")
    if len(body) > max_frame_bytes:
        raise PolicyLimitError("message exceeds frame byte limit")
    _check_depth(body)
    try:
        parsed = json.loads(
            body.decode("utf-8"), object_pairs_hook=_unique_object,
            parse_float=_reject_number, parse_constant=_reject_number,
        )
        if type(parsed) is not dict or set(parsed) != {"version", "type", "request_id", "payload"}:
            raise ProtocolError("envelope has missing or unexpected fields")
        message = Message(**parsed)
        validate_message(message)
        if serialize(parsed) != body:
            raise ProtocolError("envelope is not canonical JSON")
        return message
    except (UnicodeError, ValueError, TypeError, OverflowError, RecursionError) as error:
        raise ProtocolError("malformed envelope") from error


def _pack(value: object, encoder, max_item_bytes: int) -> str:
    _limit(max_item_bytes, "max_item_bytes")
    try:
        data = encoder(value)
    except StorageCorruptionError as error:
        raise ProtocolError("malformed signed item") from error
    if len(data) > max_item_bytes:
        raise PolicyLimitError("signed item exceeds byte limit")
    return base64.b64encode(data).decode("ascii")


def _unpack(value: str, decoder, max_item_bytes: int):
    _limit(max_item_bytes, "max_item_bytes")
    if type(value) is not str or not value:
        raise ProtocolError("signed item must be a nonempty base64 string")
    # A length cap is checked before making ASCII/base64 buffers. Padding can
    # make a string with a legal encoded size decode to up to two extra bytes.
    if len(value) > 4 * ((max_item_bytes + 2) // 3):
        raise PolicyLimitError("encoded signed item exceeds byte limit")
    try:
        data = base64.b64decode(value.encode("ascii"), validate=True)
    except (UnicodeError, ValueError, binascii.Error) as error:
        raise ProtocolError("invalid base64 signed item") from error
    if len(data) > max_item_bytes:
        raise PolicyLimitError("signed item exceeds byte limit")
    if base64.b64encode(data).decode("ascii") != value:
        raise ProtocolError("noncanonical base64 signed item")
    _check_depth(data)
    # Deliberately catch only the codec corruption exception, directly around
    # decoding. StorageError from a subsequent ledger mutation remains fatal.
    try:
        return decoder(data)
    except StorageCorruptionError as error:
        raise ProtocolError("malformed signed item") from error


def pack_transaction(transaction, *, max_item_bytes: int = MAX_ITEM_BYTES) -> str:
    return _pack(transaction, encode_transaction, max_item_bytes)


def unpack_transaction(value: str, *, max_item_bytes: int = MAX_ITEM_BYTES):
    return _unpack(value, decode_transaction, max_item_bytes)


def pack_block(block, *, max_item_bytes: int = MAX_ITEM_BYTES) -> str:
    return _pack(block, encode_block, max_item_bytes)


def unpack_block(value: str, *, max_item_bytes: int = MAX_ITEM_BYTES):
    return _unpack(value, decode_block, max_item_bytes)
