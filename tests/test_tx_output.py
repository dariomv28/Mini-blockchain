from transaction.tx_output import TxOutput

def test_tx_output():
    output = TxOutput(
        amount=6,
        recipient_address="Dang"
    )
    assert output.amount == 6
    assert output.recipient_address == "Dang"

def test_tx_output_to_dict():
    output = TxOutput(
        amount=6,
        recipient_address="PYC_test",
    )

    assert output.to_dict() == {
        "amount": 6,
        "recipient_address": "PYC_test",
    }