from crypto.address import public_key_to_address, validate_address
from crypto.hash import serialize
from crypto.keys import public_key_to_hex
from transaction.transaction import Transaction
from transaction.tx_input import TxInput
from transaction.tx_output import TxOutput


class TransactionWorkLimitError(Exception):
    """API wallet work/size limit, not a consensus rule."""


def build_signed_transaction(*, selected_utxos, sender_address, recipient_address, amount, fee, private_key, timestamp=None, max_bytes=None):
    if type(amount) is not int or amount <= 0 or type(fee) is not int or fee < 0:
        raise ValueError("Invalid amount or fee")
    if not validate_address(recipient_address) or public_key_to_address(private_key.get_verifying_key()) != sender_address:
        raise ValueError("Invalid sender or recipient")
    selected = list(selected_utxos)
    if not selected or len({item[0] for item in selected}) != len(selected):
        raise ValueError("Invalid selected outpoints")
    if any(output.recipient_address != sender_address or type(output.amount) is not int or output.amount <= 0 for _, output in selected):
        raise ValueError("Selected UTXO does not belong to sender")
    total = sum(output.amount for _, output in selected)
    change = total - amount - fee
    if change < 0:
        raise ValueError("Insufficient selected value")
    outputs = [TxOutput(amount, recipient_address)]
    if change:
        outputs.append(TxOutput(change, sender_address))
    if timestamp is not None and (type(timestamp) is not int or timestamp < 0):
        raise ValueError("Invalid timestamp")
    kwargs = {} if timestamp is None else {"timestamp": timestamp}
    tx = Transaction([TxInput(txid, index) for (txid, index), _ in selected], outputs, **kwargs)
    if max_bytes is not None:
        # ECDSA uses fixed-width raw signatures (64 bytes for SECP256k1).
        # Populate their hex width without doing any signing, using the exact
        # timestamp/output/index representation that the signed tx will retain.
        public = private_key.get_verifying_key()
        for tx_input in tx.inputs:
            tx_input.public_key = public_key_to_hex(public)
            tx_input.signature = "0" * (4 * private_key.curve.baselen)
        if len(serialize(tx.to_dict())) > max_bytes:
            raise TransactionWorkLimitError("Transaction exceeds node item limit")
    for index in range(len(tx.inputs)):
        tx.sign_input(index, private_key)
    return tx
