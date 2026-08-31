from dataclasses import dataclass

@dataclass
class TxOutput:
    amount: int
    recipient_address: str

    def to_dict(self) -> dict:
        return {
            "amount": self.amount,
            "recipient_address": self.recipient_address
        }