from transaction.tx_input import TxInput


def test_tx_input():
    tx_input = TxInput(
        previous_tx_id="abc",
        output_index=0,
    )

    assert tx_input.previous_tx_id == "abc"
    assert tx_input.output_index == 0


def test_tx_input_to_dict():
    tx_input = TxInput(
        previous_tx_id="abc",
        output_index=0,
        public_key="public",
        signature="signature",
    )

    assert tx_input.to_dict() == {
        "previous_tx_id": "abc",
        "output_index": 0,
        "public_key": "public",
        "signature": "signature",
    }


def test_outpoint_dict():
    tx_input = TxInput(
        previous_tx_id="abc",
        output_index=0,
        public_key="public",
        signature="signature",
    )

    assert tx_input.outpoint_dict() == {
        "previous_tx_id": "abc",
        "output_index": 0,
    }
