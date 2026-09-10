"""Protocol-only checks use detached objects and never open a database."""

import base64
from dataclasses import FrozenInstanceError, replace
import json
from pathlib import Path

from ecdsa import SECP256k1, SigningKey
import pytest

from blockchain.block import Block
from blockchain.genesis import GENESIS_HASH, GENESIS_TIMESTAMP, create_genesis_block
from crypto.address import public_key_to_address
from crypto.hash import serialize
from network.config import MAX_HEIGHT, NETWORK_ID, NodeConfig
from network.errors import (
    NetworkError, NodeBusyError, NodeClosedError, PeerDisconnectedError,
    PolicyLimitError, ProtocolError,
)
from network.messages import MESSAGE_TYPES, Message
from network.protocol import (
    decode_message, encode_message, pack_block, pack_transaction,
    unpack_block, unpack_transaction,
)
import network.protocol as protocol
from storage.codec import encode_block, encode_transaction
from storage.errors import StorageCorruptionError, StorageError
from transaction.transaction import Transaction
from transaction.tx_input import TxInput
from transaction.tx_output import TxOutput


TOKEN = "0123456789abcdef" * 2
KEY = SigningKey.from_secret_exponent(91, curve=SECP256k1)
ADDRESS = public_key_to_address(KEY.get_verifying_key())


def signed_transaction():
    result = Transaction([TxInput("previous-input", 0)], [TxOutput(19, ADDRESS)], timestamp=123)
    result.sign_input(0, KEY)
    return result


def messages():
    transaction = pack_transaction(signed_transaction())
    block = pack_block(create_genesis_block())
    return [
        Message("VERSION", {"network_id": NETWORK_ID, "genesis_hash": GENESIS_HASH,
                           "node_id": TOKEN, "connection_nonce": TOKEN, "listen_port": 5001,
                           "height": 0, "tip_hash": GENESIS_HASH}),
        Message("VERACK", {}), Message("GET_STATUS", {}, TOKEN),
        Message("STATUS", {"height": 0, "tip_hash": GENESIS_HASH}),
        Message("STATUS", {"height": MAX_HEIGHT, "tip_hash": GENESIS_HASH}, TOKEN),
        Message("GET_PEERS", {}, TOKEN),
        Message("PEERS", {"peers": [{"host": "127.0.0.1", "port": 65535}]}, TOKEN),
        Message("NEW_TRANSACTION", {"transaction": transaction}),
        Message("NEW_BLOCK", {"block": block}),
        Message("GET_BLOCKS", {"anchor_height": 0, "anchor_hash": GENESIS_HASH, "limit": 16}, TOKEN),
        Message("BLOCKS", {"anchor_height": 0, "anchor_hash": GENESIS_HASH, "tip_height": 1,
                          "tip_hash": GENESIS_HASH, "blocks": [block], "more": False}, TOKEN),
        Message("GET_MEMPOOL", {"tip_hash": GENESIS_HASH, "snapshot_id": None, "cursor": 0, "limit": 32}, TOKEN),
        Message("GET_MEMPOOL", {"tip_hash": GENESIS_HASH, "snapshot_id": TOKEN, "cursor": 32, "limit": 1}, TOKEN),
        Message("MEMPOOL", {"tip_hash": GENESIS_HASH, "snapshot_id": TOKEN, "cursor": 0,
                           "transactions": [transaction], "next_cursor": 1, "done": True}, TOKEN),
        Message("MEMPOOL", {"tip_hash": GENESIS_HASH, "snapshot_id": TOKEN, "cursor": 0,
                           "transactions": [], "next_cursor": 0, "done": True}, TOKEN),
        Message("PING", {"nonce": TOKEN}), Message("PONG", {"nonce": TOKEN}),
        Message("ERROR", {"code": "BAD_MESSAGE", "message": "Malformed message"}, TOKEN),
        Message("ERROR", {"code": "BUSY", "message": "Please retry"}),
    ]


def envelope(message):
    return {"version": message.version, "type": message.type,
            "request_id": message.request_id, "payload": message.payload}


@pytest.mark.parametrize("message", messages(), ids=lambda item: item.type)
def test_all_schemas_roundtrip_with_exact_length_and_canonical_body(message):
    frame = encode_message(message)
    assert int.from_bytes(frame[:4], "big") == len(frame) - 4
    assert frame[4:] == serialize(envelope(message))
    assert decode_message(frame[4:]) == message


def test_roundtrip_fixtures_cover_entire_type_allowlist():
    assert {message.type for message in messages()} == MESSAGE_TYPES


@pytest.mark.parametrize("change", [
    {"version": True}, {"version": 2}, {"version": 1.0},
    {"type": "UNKNOWN"}, {"type": []}, {"request_id": TOKEN},
    {"payload": []}, {"payload": {}}, {"payload": {"nonce": TOKEN, "extra": 1}},
    {"payload": {"nonce": TOKEN.upper()}}, {"payload": {"nonce": 1}},
])
def test_malformed_message_rejected_on_both_encode_and_decode(change):
    invalid = replace(Message("PING", {"nonce": TOKEN}), **change)
    with pytest.raises(ProtocolError):
        encode_message(invalid)
    with pytest.raises(ProtocolError):
        decode_message(serialize(envelope(invalid)))


@pytest.mark.parametrize("body", [
    b"", b"\xff", b"null", b"[]", b"true", b"{}", b"[}",
    b'{"version":1,"version":1,"payload":{},"request_id":null,"type":"VERACK"}',
    b'{"payload":{"nonce":"a","nonce":"b"},"request_id":null,"type":"PING","version":1}',
    b'{"payload":{},"request_id":null,"type":"VERACK","version":NaN}',
    b'{"payload":{},"request_id":null,"type":"VERACK","version":Infinity}',
    b'{"payload":{},"request_id":null,"type":"VERACK","version":-Infinity}',
    b'{"payload":{},"request_id":null,"type":"VERACK","version":1.0}',
    b'{"payload":{},"request_id":null,"type":"VERACK","version":1e0}',
    b'{"payload":{},"request_id":null,"type":"VERACK","version":1,"extra":0}',
    b'{"payload":{},"request_id":null,"type":"VERACK"}',
])
def test_invalid_envelopes(body):
    with pytest.raises(ProtocolError):
        decode_message(body)


@pytest.mark.parametrize("render", [
    lambda data: json.dumps(data).encode(),
    lambda data: serialize(data) + b"\n",
    lambda data: b" " + serialize(data),
    lambda data: serialize(data).replace(b'"VERACK"', b'"VERA\\u0043K"'),
])
def test_equivalent_noncanonical_json_is_rejected(render):
    with pytest.raises(ProtocolError):
        decode_message(render(envelope(Message("VERACK", {}))))


def test_depth_checked_before_json_decoder_for_envelope_and_signed_item(monkeypatch):
    def never_decode(*args, **kwargs):
        pytest.fail("recursive decoder ran before depth rejection")
    monkeypatch.setattr(protocol.json, "loads", never_decode)
    body = b"[" * 33 + b"0" + b"]" * 33
    with pytest.raises(ProtocolError, match="nesting"):
        decode_message(body)
    with pytest.raises(ProtocolError, match="nesting"):
        unpack_transaction(base64.b64encode(body).decode())


def test_depth_scanner_honors_quotes_backslashes_and_container_chars_in_strings():
    message = Message("ERROR", {"code": "BAD_MESSAGE", "message": '[{\\"' * 40})
    assert decode_message(encode_message(message)[4:]) == message


def test_frame_size_covers_json_and_base64_expansion_and_accepts_exact_boundary(monkeypatch):
    message = Message("NEW_BLOCK", {"block": pack_block(create_genesis_block())})
    frame = encode_message(message)
    raw_size = len(encode_block(create_genesis_block()))
    assert len(frame) - 4 > len(message.payload["block"]) > raw_size
    assert encode_message(message, max_frame_bytes=len(frame) - 4) == frame
    assert decode_message(frame[4:], max_frame_bytes=len(frame) - 4) == message
    with pytest.raises(PolicyLimitError):
        encode_message(message, max_frame_bytes=len(frame) - 5)
    monkeypatch.setattr(protocol.json, "loads", lambda *a, **k: pytest.fail("decoded over budget"))
    with pytest.raises(PolicyLimitError):
        decode_message(frame[4:], max_frame_bytes=len(frame) - 5)


@pytest.mark.parametrize("message", [
    Message("GET_STATUS", {}),
    Message("GET_STATUS", {}, TOKEN.upper()),
    Message("VERACK", {}, TOKEN),
    Message("STATUS", {"height": -1, "tip_hash": GENESIS_HASH}),
    Message("STATUS", {"height": True, "tip_hash": GENESIS_HASH}),
    Message("STATUS", {"height": MAX_HEIGHT + 1, "tip_hash": GENESIS_HASH}),
    Message("STATUS", {"height": 1, "tip_hash": GENESIS_HASH.upper()}),
    Message("GET_BLOCKS", {"anchor_height": 0, "anchor_hash": GENESIS_HASH, "limit": True}, TOKEN),
    Message("GET_BLOCKS", {"anchor_height": 0, "anchor_hash": GENESIS_HASH, "limit": 0}, TOKEN),
    Message("GET_BLOCKS", {"anchor_height": 0, "anchor_hash": GENESIS_HASH, "limit": 17}, TOKEN),
    Message("GET_MEMPOOL", {"tip_hash": GENESIS_HASH, "snapshot_id": None, "cursor": 1, "limit": 1}, TOKEN),
    Message("GET_MEMPOOL", {"tip_hash": GENESIS_HASH, "snapshot_id": TOKEN, "cursor": 0, "limit": 33}, TOKEN),
    Message("ERROR", {"code": "INTERNAL_EXCEPTION", "message": "error"}),
    Message("ERROR", {"code": "BAD_MESSAGE", "message": "x" * 257}),
    Message("NEW_TRANSACTION", {"transaction": "\u00e9"}),
    Message("NEW_BLOCK", {"block": ""}),
])
def test_message_field_constraints(message):
    with pytest.raises(ProtocolError):
        encode_message(message)


@pytest.mark.parametrize("change", [
    {"done": 1}, {"transactions": ["e30="] * 33, "next_cursor": 33},
    {"cursor": 1}, {"next_cursor": 2}, {"snapshot_id": None},
    {"transactions": [], "next_cursor": 0, "done": False},
])
def test_mempool_page_constraints(change):
    payload = {"tip_hash": GENESIS_HASH, "snapshot_id": TOKEN, "cursor": 0,
               "transactions": ["e30="], "next_cursor": 1, "done": True}
    with pytest.raises(ProtocolError):
        encode_message(Message("MEMPOOL", {**payload, **change}, TOKEN))


@pytest.mark.parametrize("peers", [
    [{"host": "127.0.0.1", "port": 1}] * 33,
    [{"host": "localhost", "port": 1}], [{"host": "8.8.8.8", "port": 1}],
    [{"host": "127.0.0.1", "port": True}], [{"host": "127.0.0.1", "port": 0}],
    [{"host": "127.0.0.1", "port": 65536}], [{"host": "127.0.0.1", "port": 1, "db": "x"}],
])
def test_peer_endpoint_schema(peers):
    with pytest.raises(ProtocolError):
        encode_message(Message("PEERS", {"peers": peers}, TOKEN))


def test_signed_transaction_preserves_signatures_case_hash_and_unbounded_integer_values():
    transaction = signed_transaction()
    transaction.timestamp = 2**80
    transaction.outputs[0].amount = 2**80
    transaction.sign_input(0, KEY)
    transaction.inputs[0].public_key = transaction.inputs[0].public_key.upper()
    transaction.inputs[0].signature = transaction.inputs[0].signature.upper()
    packed = pack_transaction(transaction)
    recovered = unpack_transaction(packed)
    assert encode_transaction(recovered) == encode_transaction(transaction)
    assert recovered.to_dict() == transaction.to_dict()
    assert recovered.txid() == transaction.txid()
    assert recovered.timestamp == 2**80
    assert recovered.outputs[0].amount == 2**80
    assert recovered.inputs[0].signature == transaction.inputs[0].signature
    recovered.outputs[0].amount = 1
    assert transaction.outputs[0].amount == 2**80


def test_full_block_adapter_keeps_every_signed_byte_and_hash():
    block = Block(transactions=[signed_transaction()], previous_block_hash=GENESIS_HASH,
                  timestamp=GENESIS_TIMESTAMP + 1, difficulty=16, nonce=7)
    recovered = unpack_block(pack_block(block))
    assert encode_block(recovered) == encode_block(block)
    assert recovered.hash() == block.hash()
    assert recovered.transactions[0].inputs[0].signature == block.transactions[0].inputs[0].signature
    assert unpack_block(pack_block(create_genesis_block())).hash() == GENESIS_HASH


def test_block_adapter_rejects_tampered_merkle_without_repair():
    data = create_genesis_block().to_dict()
    data["header"]["merkle_root"] = "a" * 64
    with pytest.raises(ProtocolError) as captured:
        unpack_block(base64.b64encode(serialize(data)).decode())
    assert isinstance(captured.value.__cause__, StorageCorruptionError)


@pytest.mark.parametrize("value", ["", "!!!", "e30=\n", "e30", "e30===", "e31=", "\u00e9", 1, None])
def test_base64_strictness_and_noncanonical_padding(value):
    with pytest.raises(ProtocolError):
        unpack_transaction(value)


def test_adapter_checks_encoded_length_before_allocating_and_raw_length_after_decode(monkeypatch):
    with pytest.raises(PolicyLimitError):
        unpack_transaction("e30=", max_item_bytes=1)
    monkeypatch.setattr(protocol.base64, "b64decode", lambda *a, **k: pytest.fail("decoded oversized base64"))
    with pytest.raises(PolicyLimitError):
        unpack_transaction("A" * 12, max_item_bytes=1)


def test_pack_and_unpack_allow_exact_signed_item_size():
    transaction = signed_transaction()
    byte_count = len(encode_transaction(transaction))
    packed = pack_transaction(transaction, max_item_bytes=byte_count)
    assert unpack_transaction(packed, max_item_bytes=byte_count) == transaction
    with pytest.raises(PolicyLimitError):
        pack_transaction(transaction, max_item_bytes=byte_count - 1)
    with pytest.raises(PolicyLimitError):
        unpack_transaction(packed, max_item_bytes=byte_count - 1)


@pytest.mark.parametrize("adapter", [pack_transaction, pack_block])
def test_adapter_reports_local_malformed_structures_as_protocol_error(adapter):
    with pytest.raises(ProtocolError):
        adapter(object())


def test_codec_error_mapping_is_narrow_and_does_not_hide_other_storage_errors(monkeypatch):
    payload = pack_transaction(signed_transaction())
    def raise_error(error):
        def broken(_):
            raise error
        return broken
    monkeypatch.setattr(protocol, "decode_transaction", raise_error(StorageCorruptionError("bad codec")))
    with pytest.raises(ProtocolError):
        unpack_transaction(payload)
    sentinel = StorageError("disk failed")
    monkeypatch.setattr(protocol, "decode_transaction", raise_error(sentinel))
    with pytest.raises(StorageError) as captured:
        unpack_transaction(payload)
    assert captured.value is sentinel


def test_config_defaults_and_detached_frozen_collections():
    seeds = [["127.0.0.1", 5002], ["127.0.0.1", 5002]]
    cidrs = ["127.0.0.0/8"]
    config = NodeConfig(port=0, seeds=seeds, allowed_cidrs=cidrs, db_path=Path("test.sqlite"))
    seeds[0][1] = 9999
    cidrs.clear()
    assert config.seeds == (("127.0.0.1", 5002),)
    assert config.allowed_cidrs == ("127.0.0.0/8",)
    assert config.db_path == "test.sqlite"
    assert config.max_frame_bytes == 4 * 1024 * 1024
    assert config.snapshot_max_transactions == 4096
    with pytest.raises(FrozenInstanceError):
        config.port = 10


@pytest.mark.parametrize("field,value", [
    ("port", True), ("port", -1), ("port", 65536),
    ("max_peers", 0), ("max_frame_bytes", 2**32), ("max_item_bytes", True),
    ("max_candidates", 1.5), ("inbound_max_events", -1), ("outbound_max_bytes", None),
    ("block_batch_size", 17), ("mempool_page_size", 33), ("max_requests", 5),
    ("mempool_max_transactions", 0), ("mempool_max_bytes", False),
    ("message_rate", 1.5), ("message_burst", 0), ("byte_burst", True),
    ("connect_timeout", float("nan")), ("handshake_timeout", float("inf")),
    ("request_timeout", 0), ("read_timeout", True), ("snapshot_lifetime", -1),
    ("retry_delay", "10"), ("close_timeout", 10**400),
    ("reconnect_initial", 31), ("db_path", b"bytes"), ("db_path", ""), ("db_path", "a\x00b"),
    ("seeds", "127.0.0.1:1"), ("seeds", (("127.0.0.1", 0),)),
    ("seeds", (("127.0.0.1",),)), ("allowed_cidrs", ()),
])
def test_invalid_config_rejected(field, value):
    with pytest.raises(ValueError):
        NodeConfig(**{field: value})


@pytest.mark.parametrize("host", [
    "localhost", "http://127.0.0.1", "127.0.0.1:5001", "127.1", "127.00.0.1",
    "::1", "0.0.0.0", "8.8.8.8", "169.254.1.1", "224.0.0.1", "255.255.255.255",
    "100.64.0.1", "192.0.0.1", "127.255.255.255", "127.0.0.0", "192.168.1.1", 2130706433,
])
def test_default_policy_rejects_nonloopback_or_nonhost_endpoints(host):
    with pytest.raises(ValueError):
        NodeConfig().validate_endpoint(host, 1)


@pytest.mark.parametrize("cidrs", [
    ("0.0.0.0/0",), ("8.8.8.0/24",), ("169.254.0.0/16",), ("::1/128",),
    ("192.168.1.1/24",), ("10.0.0.1",), ("172.0.0.0/8",), (123,),
])
def test_allowlist_cannot_enable_public_or_ambiguous_networks(cidrs):
    with pytest.raises(ValueError):
        NodeConfig(allowed_cidrs=cidrs)


def test_lan_requires_explicit_scope_and_excludes_subnet_broadcast():
    config = NodeConfig(host="192.168.1.10", allowed_cidrs=("192.168.1.0/24", "127.0.0.0/8"))
    assert config.validate_endpoint("192.168.1.20", 1234) == ("192.168.1.20", 1234)
    assert config.validate_endpoint("127.0.0.1", 1) == ("127.0.0.1", 1)
    for address in ("192.168.1.0", "192.168.1.255", "192.168.2.1"):
        with pytest.raises(ValueError):
            config.validate_endpoint(address, 1)
    assert NodeConfig(host="10.1.2.3", allowed_cidrs=("10.1.2.3/32",)).host == "10.1.2.3"


def test_network_exceptions_do_not_inherit_storage_failures():
    for error in (ProtocolError, PolicyLimitError, PeerDisconnectedError, NodeClosedError, NodeBusyError):
        assert issubclass(error, NetworkError)
        assert not issubclass(error, StorageError)
    assert not issubclass(PolicyLimitError, ProtocolError)
