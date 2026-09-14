import pytest

from transaction.tx_output import TxOutput
from wallet.coin_selection import InsufficientBalanceError, select_utxos


def test_selection_is_deterministic_and_includes_fee():
    a, b, c = ("a"*64, 0), ("b"*64, 0), ("c"*64, 0)
    coins = {c: TxOutput(20, "sender"), b: TxOutput(5, "sender"), a: TxOutput(5, "sender")}
    exact = select_utxos(coins, amount=9, fee=1)
    assert [point for point, _ in exact.selected] == [a, b]
    assert exact.total == 10 and exact.change == 0
    change = select_utxos(dict(reversed(list(coins.items()))), amount=10, fee=1)
    assert [point for point, _ in change.selected] == [a, b, c]
    assert change.total == 30 and change.change == 19
    assert len(coins) == 3
    with pytest.raises(InsufficientBalanceError):
        select_utxos(coins, amount=30, fee=1)


@pytest.mark.parametrize("amount,fee", [(0,0), (-1,0), (True,0), (1,False), (1,-1), (1.0,0), (1,"0")])
def test_invalid_amount_or_fee(amount, fee):
    with pytest.raises(ValueError):
        select_utxos({}, amount=amount, fee=fee)
