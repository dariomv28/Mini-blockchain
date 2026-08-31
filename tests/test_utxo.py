from transaction.tx_output import TxOutput
from transaction.utxo import UTXOSet


def test_add_and_get_utxo():
    utxos = UTXOSet()

    output = TxOutput(
        amount=10,
        recipient_address="Alice",
    )

    utxos.add(
        "tx1",
        0,
        output,
    )

    assert utxos.exists(
        "tx1",
        0,
    )

    assert utxos.get(
        "tx1",
        0,
    ) == output


def test_spend_utxo():
    utxos = UTXOSet()

    output = TxOutput(
        amount=10,
        recipient_address="Alice",
    )

    utxos.add(
        "tx1",
        0,
        output,
    )

    utxos.spend(
        "tx1",
        0,
    )

    assert not utxos.exists(
        "tx1",
        0,
    )


def test_get_balance():
    utxos = UTXOSet()

    utxos.add(
        "tx1",
        0,
        TxOutput(5, "Alice"),
    )

    utxos.add(
        "tx2",
        0,
        TxOutput(3, "Alice"),
    )

    utxos.add(
        "tx3",
        0,
        TxOutput(7, "Bob"),
    )

    assert utxos.get_balance(
        "Alice"
    ) == 8

    assert utxos.get_balance(
        "Bob"
    ) == 7
