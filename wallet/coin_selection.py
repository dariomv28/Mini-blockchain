from dataclasses import dataclass


class InsufficientBalanceError(Exception):
    pass


@dataclass(frozen=True)
class Selection:
    selected: list
    total: int
    change: int


def select_utxos(utxos, *, amount: int, fee: int) -> Selection:
    if type(amount) is not int or amount <= 0 or type(fee) is not int or fee < 0:
        raise ValueError("amount must be positive and fee nonnegative integers")
    selected, total = [], 0
    for outpoint, output in sorted(utxos.items(), key=lambda item: (item[1].amount, item[0][0], item[0][1])):
        if type(output.amount) is not int or output.amount <= 0:
            raise ValueError("Invalid UTXO amount")
        selected.append((outpoint, output))
        total += output.amount
        if total >= amount + fee:
            return Selection(selected, total, total - amount - fee)
    raise InsufficientBalanceError("Insufficient available balance")
