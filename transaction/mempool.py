"""Bounded in-memory pending transactions with deterministic miner selection."""

from copy import deepcopy
from dataclasses import dataclass
from fractions import Fraction

from crypto.hash import serialize
from transaction.transaction import Transaction
from transaction.utxo import UTXOSet
from transaction.validation import calculate_transaction_fee


DEFAULT_MEMPOOL_MAX_TRANSACTIONS = 1000
DEFAULT_MEMPOOL_MAX_BYTES = 1_000_000
DEFAULT_BLOCK_MAX_TRANSACTIONS = 100
DEFAULT_BLOCK_MAX_BYTES = 100_000


@dataclass(frozen=True)
class MempoolEntry:
    transaction: Transaction
    fee: int
    size_bytes: int

    @property
    def fee_rate(self) -> Fraction:
        return Fraction(self.fee, self.size_bytes)


def _check_limit(value: int, name: str, *, allow_zero: bool) -> None:
    if type(value) is not int or value < (0 if allow_zero else 1):
        qualifier = "non-negative" if allow_zero else "positive"
        raise ValueError(f"{name} must be a {qualifier} integer")


class Mempool:
    """First-seen transactions validated against confirmed and pending UTXOs.

    Public transaction access returns snapshots. A pending child must arrive
    after its parents; neither orphan storage nor replacement is supported.
    """

    def __init__(
        self,
        utxo_set: UTXOSet | None = None,
        seen_txids: set[str] | None = None,
        *,
        max_transactions: int = DEFAULT_MEMPOOL_MAX_TRANSACTIONS,
        max_bytes: int = DEFAULT_MEMPOOL_MAX_BYTES,
    ) -> None:
        _check_limit(max_transactions, "max_transactions", allow_zero=False)
        _check_limit(max_bytes, "max_bytes", allow_zero=False)
        if (utxo_set is None) != (seen_txids is None):
            raise ValueError("utxo_set and seen_txids must be supplied together")
        if utxo_set is not None and not isinstance(utxo_set, UTXOSet):
            raise ValueError("utxo_set must be a UTXOSet")
        if seen_txids is not None and (
            not isinstance(seen_txids, set)
            or not all(isinstance(txid, str) for txid in seen_txids)
        ):
            raise ValueError("seen_txids must be a set of transaction ID strings")

        self._max_transactions = max_transactions
        self._max_bytes = max_bytes
        self._confirmed_utxos = UTXOSet() if utxo_set is None else utxo_set.copy()
        self._seen_txids = set() if seen_txids is None else set(seen_txids)
        self._working_utxos = self._confirmed_utxos.copy()
        self._entries: dict[str, MempoolEntry] = {}
        self._total_bytes = 0

    def __len__(self) -> int:
        return len(self._entries)

    @property
    def total_bytes(self) -> int:
        return self._total_bytes

    @property
    def max_transactions(self) -> int:
        return self._max_transactions

    @property
    def max_bytes(self) -> int:
        return self._max_bytes

    def copy(self) -> "Mempool":
        snapshot = Mempool(
            self._confirmed_utxos,
            self._seen_txids,
            max_transactions=self.max_transactions,
            max_bytes=self.max_bytes,
        )
        snapshot._working_utxos = self._working_utxos.copy()
        snapshot._entries = deepcopy(self._entries)
        snapshot._total_bytes = self._total_bytes
        return snapshot

    def has_transaction(self, txid: str) -> bool:
        return isinstance(txid, str) and txid in self._entries

    def get_transaction(self, txid: str) -> Transaction | None:
        entry = self.get_entry(txid)
        return None if entry is None else entry.transaction

    def get_entry(self, txid: str) -> MempoolEntry | None:
        if not self.has_transaction(txid):
            return None
        return deepcopy(self._entries[txid])

    def get_transactions(self) -> list[Transaction]:
        """Return insertion order, which places every pending parent first."""
        return [deepcopy(entry.transaction) for entry in self._entries.values()]

    def add_transaction(self, transaction: Transaction) -> bool:
        """Validate and reserve inputs atomically; reject invalid/capacity cases."""
        if not isinstance(transaction, Transaction):
            return False
        if len(self) >= self.max_transactions:
            return False

        try:
            candidate = deepcopy(transaction)
            fee = calculate_transaction_fee(candidate, self._working_utxos)
            txid = candidate.txid()
            if txid in self._seen_txids or txid in self._entries:
                return False
            size_bytes = len(serialize(candidate.to_dict()))
            if self.total_bytes + size_bytes > self.max_bytes:
                return False
            # Apply on a copy so a collision or other invalid transition cannot
            # alter reservations or expose a partially admitted transaction.
            updated_utxos = self._working_utxos.copy()
            updated_utxos.apply_valid_transaction(candidate)
        except (AttributeError, IndexError, KeyError, TypeError, ValueError):
            return False

        self._entries[txid] = MempoolEntry(candidate, fee, size_bytes)
        self._working_utxos = updated_utxos
        self._total_bytes += size_bytes
        return True

    def remove_transaction(self, txid: str) -> bool:
        """Remove an entry and descendants invalidated by its missing outputs."""
        if not self.has_transaction(txid):
            return False
        rebuilt = Mempool(
            self._confirmed_utxos,
            self._seen_txids,
            max_transactions=self.max_transactions,
            max_bytes=self.max_bytes,
        )
        for entry_txid, entry in self._entries.items():
            if entry_txid != txid:
                rebuilt.add_transaction(entry.transaction)
        self._entries = rebuilt._entries
        self._working_utxos = rebuilt._working_utxos
        self._total_bytes = rebuilt._total_bytes
        return True

    def revalidated(self, utxo_set: UTXOSet, seen_txids: set[str]) -> "Mempool":
        """Return a new pool replayed against the newly confirmed chain state."""
        rebuilt = Mempool(
            utxo_set,
            seen_txids,
            max_transactions=self.max_transactions,
            max_bytes=self.max_bytes,
        )
        for txid, entry in self._entries.items():
            if txid not in rebuilt._seen_txids:
                rebuilt.add_transaction(entry.transaction)
        return rebuilt

    def select_transactions(
        self,
        *,
        max_transactions: int = DEFAULT_BLOCK_MAX_TRANSACTIONS,
        max_bytes: int = DEFAULT_BLOCK_MAX_BYTES,
    ) -> list[Transaction]:
        """Greedily choose ready entries by fee/byte, breaking ties by TXID.

        Bounds count regular transactions and their signed canonical bytes only.
        An oversized entry is skipped; its pending descendants remain unready.
        This is individual fee-rate selection, not package/CPFP optimization.
        """
        _check_limit(max_transactions, "max_transactions", allow_zero=True)
        _check_limit(max_bytes, "max_bytes", allow_zero=True)
        ranked = sorted(
            self._entries,
            key=lambda txid: (-self._entries[txid].fee_rate, txid),
        )
        parents = {
            txid: {
                tx_input.previous_tx_id
                for tx_input in entry.transaction.inputs
                if tx_input.previous_tx_id in self._entries
            }
            for txid, entry in self._entries.items()
        }
        selected: list[Transaction] = []
        selected_txids: set[str] = set()
        total_bytes = 0
        while len(selected) < max_transactions:
            for txid in ranked:
                entry = self._entries[txid]
                if txid in selected_txids or not parents[txid] <= selected_txids:
                    continue
                if total_bytes + entry.size_bytes > max_bytes:
                    continue
                selected.append(deepcopy(entry.transaction))
                selected_txids.add(txid)
                total_bytes += entry.size_bytes
                break
            else:
                break
        return selected
