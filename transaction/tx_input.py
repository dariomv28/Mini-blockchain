from dataclasses import dataclass

@dataclass
class TxInput:
    previous_tx_id: str
    output_index: int
    public_key: str = ""
    signature: str = ""

    def to_dict(self, include_signature: bool = True) -> dict:
        data = {
            "previous_tx_id": self.previous_tx_id,
            "output_index": self.output_index,
            "public_key": self.public_key,
        }
        if include_signature:
            data["signature"] = self.signature

        return data

    def outpoint_dict(self) -> dict:
        return {
            "previous_tx_id": self.previous_tx_id,
            "output_index": self.output_index,
        }
