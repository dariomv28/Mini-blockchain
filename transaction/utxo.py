from copy import deepcopy

from transaction.transaction import Transaction
from transaction.tx_output import TxOutput


class UTXOSet:
    def __init__(self):
        self._utxos: dict[tuple[str, int], TxOutput] = {}

    def __len__(self) -> int:
        return len(self._utxos)

    def copy(self) -> "UTXOSet":
        snapshot = UTXOSet()
        snapshot._utxos = self.to_dict()
        return snapshot

    def to_dict(self) -> dict[tuple[str, int], TxOutput]:
        """Return an independent in-memory snapshot keyed by outpoint."""
        return deepcopy(self._utxos)

    def add(self, txid: str, output_index: int, output: TxOutput) -> None:
        outpoint = (txid, output_index)
        if outpoint in self._utxos:
            raise ValueError("UTXO outpoint already exists")
        self._utxos[outpoint] = deepcopy(output)

    def get(self, txid: str, output_index: int) -> TxOutput | None:
        return deepcopy(self._utxos.get((txid, output_index)))

    def exists(self, txid: str, output_index: int) -> bool:
        return (txid, output_index) in self._utxos

    def spend(self, txid: str, output_index: int) -> TxOutput:
        outpoint = (txid, output_index)
        output = deepcopy(self._utxos[outpoint])
        del self._utxos[outpoint]
        return output

    def get_utxos_for_address(self, address: str) -> dict[tuple[str, int], TxOutput]:
        return {
            outpoint: deepcopy(output)
            for outpoint, output in self._utxos.items()
            if output.recipient_address == address
        }

    def get_balance(self, address: str) -> int:
        return sum(
            output.amount
            for output in self._utxos.values()
            if output.recipient_address == address
        )

    def _transaction_outputs(
        self, transaction: Transaction
    ) -> dict[tuple[str, int], TxOutput]:
        txid = transaction.txid()
        outputs = {
            (txid, index): deepcopy(output)
            for index, output in enumerate(transaction.outputs)
        }
        if any(outpoint in self._utxos for outpoint in outputs):
            raise ValueError("Transaction would overwrite an existing UTXO")
        return outputs

    def add_transaction_outputs(self, transaction: Transaction) -> None:
        # Preflight the entire batch so a later collision cannot add a prefix.
        outputs = self._transaction_outputs(transaction)
        self._utxos.update(outputs)

    def apply_valid_transaction(self, transaction: Transaction) -> None:
        """Apply an already validated transaction without partial state changes."""
        spent = [
            (tx_input.previous_tx_id, tx_input.output_index)
            for tx_input in transaction.inputs
        ]
        if len(set(spent)) != len(spent):
            raise ValueError("Transaction spends the same UTXO more than once")
        for outpoint in spent:
            if outpoint not in self._utxos:
                raise KeyError(outpoint)
        outputs = self._transaction_outputs(transaction)

        updated = dict(self._utxos)
        for outpoint in spent:
            del updated[outpoint]
        updated.update(outputs)
        self._utxos = updated
