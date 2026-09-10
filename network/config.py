"""Validated local networking policy, independent of ledger consensus."""

from dataclasses import dataclass, field, fields
from ipaddress import IPv4Address, IPv4Network
import math
import os


PROTOCOL_VERSION = 1
NETWORK_ID = "mini-blockchain-v1"
MAX_FRAME_BYTES = 4 * 1024 * 1024
MAX_ITEM_BYTES = 2 * 1024 * 1024
MAX_HEIGHT = 2**63 - 1
MAX_BLOCK_BATCH = 16
MAX_MEMPOOL_PAGE = 32
MAX_PEER_ENDPOINTS = 32

_LOCAL_NETWORKS = tuple(map(IPv4Network, (
    "127.0.0.0/8", "10.0.0.0/8", "172.16.0.0/12", "192.168.0.0/16",
)))


def local_ipv4(host: object) -> IPv4Address:
    """Accept only IPv4 literals in loopback or explicitly private ranges."""
    if type(host) is not str:
        raise ValueError("host must be an IPv4 literal")
    try:
        address = IPv4Address(host)
    except ValueError as error:
        raise ValueError("host must be an IPv4 literal") from error
    if not any(address in network for network in _LOCAL_NETWORKS):
        raise ValueError("host must be loopback or RFC1918 IPv4")
    if any(address == network.broadcast_address for network in _LOCAL_NETWORKS):
        raise ValueError("broadcast addresses are not peer endpoints")
    return address


def _positive_integer(value: object, name: str) -> None:
    if type(value) is not int or value <= 0:
        raise ValueError(f"{name} must be a positive integer")


@dataclass(frozen=True)
class NodeConfig:
    host: str = "127.0.0.1"
    port: int = 5001
    db_path: str | os.PathLike | None = None
    seeds: tuple[tuple[str, int], ...] = ()
    allowed_cidrs: tuple[str, ...] = ("127.0.0.0/8",)
    mempool_max_transactions: int | None = None
    mempool_max_bytes: int | None = None
    max_peers: int = 8
    max_concurrent_dials: int = 2
    max_frame_bytes: int = MAX_FRAME_BYTES
    max_item_bytes: int = MAX_ITEM_BYTES
    inbound_max_events: int = 128
    inbound_max_bytes: int = 16 * 1024 * 1024
    outbound_max_frames: int = 64
    outbound_max_bytes: int = 8 * 1024 * 1024
    max_requests: int = 4
    block_batch_size: int = MAX_BLOCK_BATCH
    mempool_page_size: int = MAX_MEMPOOL_PAGE
    snapshot_max_transactions: int = 4096
    snapshot_max_bytes: int = 4 * 1024 * 1024
    snapshot_global_bytes: int = 16 * 1024 * 1024
    connect_timeout: float = 5
    handshake_timeout: float = 5
    request_timeout: float = 10
    read_timeout: float = 90
    body_timeout: float = 10
    write_timeout: float = 10
    close_timeout: float = 5
    ping_interval: float = 30
    pong_timeout: float = 10
    status_interval: float = 15
    mempool_refresh_interval: float = 60
    snapshot_idle_timeout: float = 30
    snapshot_lifetime: float = 300
    snapshot_cooldown: float = 10
    retry_delay: float = 10
    reconnect_initial: float = 1
    reconnect_max: float = 30
    maintenance_interval: float = 0.25
    message_rate: int = 100
    message_burst: int = 200
    byte_rate: int = 8 * 1024 * 1024
    byte_burst: int = 16 * 1024 * 1024
    service_rate: int = 10
    service_burst: int = 20
    discovery_interval: float = 30
    candidate_ttl: float = 600
    max_candidates: int = 128
    _networks: tuple[IPv4Network, ...] = field(init=False, repr=False, compare=False)

    def __post_init__(self) -> None:
        if type(self.allowed_cidrs) not in (tuple, list) or not self.allowed_cidrs:
            raise ValueError("allowed_cidrs must be a nonempty list of IPv4 CIDRs")
        networks = []
        for cidr in self.allowed_cidrs:
            if type(cidr) is not str or "/" not in cidr:
                raise ValueError("allowlist entries must be IPv4 CIDR strings")
            try:
                network = IPv4Network(cidr, strict=True)
            except ValueError as error:
                raise ValueError("invalid IPv4 allowlist CIDR") from error
            if not any(network.subnet_of(scope) for scope in _LOCAL_NETWORKS):
                raise ValueError("allowlist CIDRs must be loopback or RFC1918 subnets")
            networks.append(network)
        object.__setattr__(self, "_networks", tuple(networks))
        object.__setattr__(self, "allowed_cidrs", tuple(str(n) for n in networks))
        object.__setattr__(self, "host", self.validate_host(self.host))
        if type(self.port) is not int or not 0 <= self.port <= 65535:
            raise ValueError("bind port must be an integer from 0 to 65535")
        if self.db_path is not None:
            try:
                path = os.fspath(self.db_path)
            except TypeError as error:
                raise ValueError("db_path must be a filesystem path or None") from error
            if type(path) is not str or not path or "\x00" in path:
                raise ValueError("db_path must be a nonempty text filesystem path")
            object.__setattr__(self, "db_path", path)
        if type(self.seeds) not in (tuple, list):
            raise ValueError("seeds must be a list of (host, port) endpoints")
        seeds = []
        for endpoint in self.seeds:
            if type(endpoint) not in (tuple, list) or len(endpoint) != 2:
                raise ValueError("each seed must contain host and port")
            normalized = self.validate_endpoint(*endpoint)
            if normalized not in seeds:
                seeds.append(normalized)
        object.__setattr__(self, "seeds", tuple(seeds))

        special = {"host", "port", "db_path", "seeds", "allowed_cidrs", "_networks"}
        durations = {
            "connect_timeout", "handshake_timeout", "request_timeout", "read_timeout",
            "body_timeout", "write_timeout", "close_timeout", "ping_interval",
            "pong_timeout", "status_interval", "mempool_refresh_interval",
            "snapshot_idle_timeout", "snapshot_lifetime", "snapshot_cooldown",
            "retry_delay", "reconnect_initial", "reconnect_max", "maintenance_interval",
            "discovery_interval", "candidate_ttl",
        }
        for item in fields(self):
            if item.name in special:
                continue
            value = getattr(self, item.name)
            if item.name in ("mempool_max_transactions", "mempool_max_bytes") and value is None:
                continue
            if item.name in durations:
                try:
                    valid = type(value) in (int, float) and value > 0 and math.isfinite(value)
                except OverflowError:
                    valid = False
                if not valid:
                    raise ValueError(f"{item.name} must be finite and positive")
            else:
                _positive_integer(value, item.name)
        for name, maximum in (
            ("max_frame_bytes", 2**32 - 1), ("max_requests", 4),
            ("block_batch_size", MAX_BLOCK_BATCH), ("mempool_page_size", MAX_MEMPOOL_PAGE),
        ):
            if getattr(self, name) > maximum:
                raise ValueError(f"{name} exceeds protocol maximum {maximum}")
        if self.reconnect_initial > self.reconnect_max:
            raise ValueError("reconnect_initial must not exceed reconnect_max")

    def validate_host(self, host: object) -> str:
        address = local_ipv4(host)
        matching = [network for network in self._networks if address in network]
        if not matching:
            raise ValueError("host is outside allowed_cidrs")
        # /31 and /32 are point-to-point or explicit host scopes, with no
        # directed broadcast. Use the most specific configured subnet otherwise.
        network = max(matching, key=lambda item: item.prefixlen)
        if network.prefixlen < 31 and address in (network.network_address, network.broadcast_address):
            raise ValueError("subnet network/broadcast addresses are not endpoints")
        return str(address)

    def validate_endpoint(self, host: object, port: object) -> tuple[str, int]:
        if type(port) is not int or not 1 <= port <= 65535:
            raise ValueError("peer port must be an integer from 1 to 65535")
        return self.validate_host(host), port
