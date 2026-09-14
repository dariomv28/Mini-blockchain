import pytest
from ecdsa import SECP256k1, SigningKey

from crypto.address import public_key_to_address
from transaction.utxo import UTXOSet
from transaction.tx_output import TxOutput
from transaction.validation import calculate_transaction_fee, validate_transaction
from wallet.transaction_builder import build_signed_transaction
from wallet.transaction_builder import TransactionWorkLimitError
from transaction.transaction import Transaction
from storage.codec import encode_transaction
from unittest.mock import patch


@pytest.mark.parametrize("amount,fee", [(10, 1), (19, 1), (20, 0)])
def test_size_preflight_rejects_before_signing_and_accepts_exact_budget(amount, fee):
    key = SigningKey.from_secret_exponent(501, curve=SECP256k1)
    sender = public_key_to_address(key.get_verifying_key())
    recipient = public_key_to_address(SigningKey.from_secret_exponent(502, curve=SECP256k1).get_verifying_key())
    kwargs = dict(selected_utxos=[(("a" * 64, 123), TxOutput(20, sender))], sender_address=sender,
                  recipient_address=recipient, amount=amount, fee=fee, private_key=key, timestamp=1234567890)
    expected = build_signed_transaction(**kwargs)
    size = len(encode_transaction(expected))
    with patch.object(Transaction, "sign_input") as sign:
        with pytest.raises(TransactionWorkLimitError):
            build_signed_transaction(**kwargs, max_bytes=size - 1)
        sign.assert_not_called()
    actual = build_signed_transaction(**kwargs, max_bytes=size)
    assert encode_transaction(actual) == encode_transaction(expected)


@pytest.mark.parametrize("amount,fee,outputs", [(10,1,[10,9]), (19,1,[19]), (20,0,[20])])
def test_real_core_accepts_all_signed_inputs_and_change(amount, fee, outputs):
    key = SigningKey.from_secret_exponent(501, curve=SECP256k1)
    sender = public_key_to_address(key.get_verifying_key())
    recipient = public_key_to_address(SigningKey.from_secret_exponent(502, curve=SECP256k1).get_verifying_key())
    coins = {(str(i)*64, 0): TxOutput(10, sender) for i in (1,2)}
    tx = build_signed_transaction(selected_utxos=coins.items(), sender_address=sender, recipient_address=recipient,
                                  amount=amount, fee=fee, private_key=key, timestamp=123)
    assert [(i.previous_tx_id, i.output_index) for i in tx.inputs] == list(coins)
    assert all(i.signature and i.public_key for i in tx.inputs)
    assert [o.amount for o in tx.outputs] == outputs
    assert tx.outputs[0].recipient_address == recipient
    if len(tx.outputs) == 2:
        assert tx.outputs[1].recipient_address == sender
    utxo = UTXOSet()
    for (txid,index), output in coins.items():
        utxo.add(txid, index, output)
    assert validate_transaction(tx, utxo)
    assert calculate_transaction_fee(tx, utxo) == fee


def test_builder_rejects_wrong_key_and_foreign_or_duplicate_coins():
    key = SigningKey.from_secret_exponent(501, curve=SECP256k1)
    sender = public_key_to_address(key.get_verifying_key())
    point = ("a" * 64, 0)
    kwargs = dict(sender_address=sender, recipient_address=sender, amount=1, fee=0, private_key=key)
    for selected in [[(point,TxOutput(5,"foreign"))], [(point,TxOutput(5,sender))]*2]:
        with pytest.raises(ValueError):
            build_signed_transaction(selected_utxos=selected, **kwargs)
