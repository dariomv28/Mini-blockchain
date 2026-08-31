from transaction.transaction import Transaction
from transaction.tx_output import TxOutput


class UTXOSet:
    def __init__(self):
        self._utxos: dict[tuple[str, int], TxOutput] = {}

    def add(self, txid: str, output_index: int, output: TxOutput) -> None:
        self._utxos[(txid, output_index)] = output

    def get(self, txid: str, output_index: int) -> TxOutput | None:
        return self._utxos.get((txid, output_index))

    def exists(
        self,
        txid: str,
        output_index: int,
    ) -> bool:

        return (
            txid,
            output_index,
        ) in self._utxos

    def spend(
        self,
        txid: str,
        output_index: int,
    ) -> TxOutput:

        return self._utxos.pop(
            (txid, output_index)
        )

    def get_balance(
        self,
        address: str,
    ) -> int:

        total = 0

        for output in self._utxos.values():
            if (
                output.recipient_address
                == address
            ):
                total += output.amount

        return total

    def add_transaction_outputs(
        self,
        transaction: Transaction,
    ) -> None:

        txid = transaction.txid()

        for output_index, output in enumerate(
            transaction.outputs
        ):
            self.add(
                txid,
                output_index,
                output,
            )

    def apply_valid_transaction(
        self,
        transaction: Transaction,
    ) -> None:

        # Xóa UTXO cũ đã bị tiêu.
        for tx_input in transaction.inputs:
            self.spend(
                tx_input.previous_tx_id,
                tx_input.output_index,
            )

        # Tạo UTXO mới.
        self.add_transaction_outputs(
            transaction
        )
