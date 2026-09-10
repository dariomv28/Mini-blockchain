"""Bounded discovery candidates and reconnect scheduling without socket tasks."""

from __future__ import annotations

from dataclasses import dataclass
import random
import time

Endpoint = tuple[str, int]


@dataclass
class _Candidate:
    endpoint: Endpoint
    seed: bool
    seen_at: float
    next_attempt: float
    attempts: int = 0
    cycle_started: float | None = None
    dialing: bool = False
    connected: bool = False
    verified: bool = False


class PeerManager:
    """Maintain finite endpoint hints; the Node owns slots and socket lifecycle.

    A discovered address is never advertised until ``mark_connected`` records a
    successful handshake. Repeated discovery does not reset retry counters.
    Call ``mark_attempt`` before launching a dial and ``mark_disconnected`` on
    either dial failure or connection loss. Every query expires stale hints.
    """

    def __init__(self, config, *, clock=time.monotonic, rng=None):
        self.config = config
        self._clock = clock
        self._rng = rng if rng is not None else random.Random()
        self._entries: dict[Endpoint, _Candidate] = {}
        self._self_endpoint: Endpoint | None = None
        self._max_count = config.max_candidates
        self._ttl = config.candidate_ttl
        self._initial_backoff = config.reconnect_initial
        self._max_backoff = config.reconnect_max
        self._max_attempts = 3
        self._cooldown = 300.0
        for endpoint in config.seeds:
            self.add_candidate(endpoint, seed=True)

    def _validate(self, endpoint) -> Endpoint:
        if not isinstance(endpoint, (tuple, list)) or len(endpoint) != 2:
            raise ValueError("endpoint must contain an IPv4 host and port")
        return self.config.validate_endpoint(endpoint[0], endpoint[1])

    def set_self_endpoint(self, endpoint: Endpoint) -> None:
        endpoint = self._validate(endpoint)
        self._self_endpoint = endpoint
        self._entries.pop(endpoint, None)

    def expire(self) -> None:
        now = self._clock()
        for endpoint, entry in list(self._entries.items()):
            if (
                not entry.seed
                and not entry.connected
                and not entry.dialing
                and now - entry.seen_at >= self._ttl
            ):
                del self._entries[endpoint]

    @property
    def candidates(self) -> list[Endpoint]:
        self.expire()
        return list(self._entries)

    @property
    def known_endpoints(self) -> list[Endpoint]:
        self.expire()
        return [entry.endpoint for entry in self._entries.values() if entry.verified]

    def add_candidate(self, endpoint: Endpoint, *, seed: bool = False) -> bool:
        endpoint = self._validate(endpoint)
        if endpoint == self._self_endpoint:
            return False
        self.expire()
        now = self._clock()
        entry = self._entries.get(endpoint)
        if entry is not None:
            entry.seen_at = now
            entry.seed = entry.seed or seed
            return False
        if len(self._entries) >= self._max_count:
            # Explicit operator seeds can displace one inactive discovery hint.
            removable = [
                item for item in self._entries.values()
                if not item.seed and not item.connected and not item.dialing
            ]
            if not seed or not removable:
                return False
            victim = min(removable, key=lambda item: item.seen_at)
            del self._entries[victim.endpoint]
        self._entries[endpoint] = _Candidate(endpoint, seed, now, now)
        return True

    def due_candidates(self, limit: int | None = None) -> list[Endpoint]:
        self.expire()
        now = self._clock()
        eligible = []
        for entry in self._entries.values():
            if entry.connected or entry.dialing or entry.next_attempt > now:
                continue
            if (
                not entry.seed
                and entry.attempts >= self._max_attempts
                and entry.cycle_started is not None
                and now < entry.cycle_started + self._cooldown
            ):
                continue
            eligible.append(entry)
        eligible.sort(key=lambda entry: (not entry.seed, entry.next_attempt, entry.endpoint))
        endpoints = [entry.endpoint for entry in eligible]
        return endpoints if limit is None else endpoints[:max(0, limit)]

    def _backoff(self, entry: _Candidate) -> float:
        # Clamp the exponent too: a long-lived dead seed has no unbounded int.
        exponent = min(max(0, entry.attempts - 1), 32)
        nominal = min(self._max_backoff, self._initial_backoff * 2 ** exponent)
        return min(self._max_backoff, nominal * self._rng.uniform(0.8, 1.2))

    def mark_attempt(self, endpoint: Endpoint) -> bool:
        endpoint = self._validate(endpoint)
        self.expire()
        entry = self._entries.get(endpoint)
        if entry is None:
            if not self.add_candidate(endpoint):
                return False
            entry = self._entries[endpoint]
        now = self._clock()
        if entry.connected or entry.dialing or entry.next_attempt > now:
            return False
        if entry.cycle_started is None or now >= entry.cycle_started + self._cooldown:
            if not entry.seed:
                entry.attempts = 0
            entry.cycle_started = now
        if not entry.seed and entry.attempts >= self._max_attempts:
            return False
        entry.attempts = min(entry.attempts + 1, 2 ** 31 - 1)
        entry.dialing = True
        entry.next_attempt = now + self._backoff(entry)
        if not entry.seed and entry.attempts >= self._max_attempts:
            entry.next_attempt = max(
                entry.next_attempt, entry.cycle_started + self._cooldown
            )
        return True

    def mark_connected(self, endpoint: Endpoint) -> bool:
        """Record successful VERSION/VERACK completion at the listen endpoint."""
        endpoint = self._validate(endpoint)
        if endpoint == self._self_endpoint:
            return False
        entry = self._entries.get(endpoint)
        if entry is None:
            if not self.add_candidate(endpoint):
                return False
            entry = self._entries[endpoint]
        entry.connected = True
        entry.dialing = False
        entry.verified = True
        entry.seen_at = self._clock()
        entry.attempts = 0
        entry.cycle_started = None
        entry.next_attempt = float("inf")
        return True

    def mark_disconnected(self, endpoint: Endpoint) -> None:
        endpoint = self._validate(endpoint)
        entry = self._entries.get(endpoint)
        if entry is None:
            return
        was_connected = entry.connected
        entry.connected = False
        entry.dialing = False
        now = self._clock()
        if was_connected:
            entry.seen_at = now
            entry.next_attempt = now + self._backoff(entry)
        else:
            entry.next_attempt = max(entry.next_attempt, now + self._backoff(entry))
