import time
from dataclasses import dataclass, field

from ecdsa import SigningKey

from crypto.hash import serialize, sha256_hex
from crypto.keys import (
    get_public_key,
    public_key_to_hex,
)
from crypto.signature import sign_message

from transaction.tx_input import TxInput
from transaction.tx_output import TxOutput


@dataclass
class Transaction:
    inputs: list[TxInput]
    outputs: list[TxOutput]

    timestamp: int = field(
        default_factory=lambda: int(time.time())
    )

    version: int = 1

    def to_dict(
        self,
        include_signatures: bool = True,
    ) -> dict:

        return {
            "version": self.version,

            "inputs": [
                tx_input.to_dict(
                    include_signature=include_signatures
                )
                for tx_input in self.inputs
            ],

            "outputs": [
                tx_output.to_dict()
                for tx_output in self.outputs
            ],

            "timestamp": self.timestamp,
        }

    def signing_dict(
        self,
        input_index: int,
    ) -> dict:

        if (
            input_index < 0
            or input_index >= len(self.inputs)
        ):
            raise IndexError(
                "input_index out of range"
            )

        return {
            "version": self.version,

            "inputs": [
                tx_input.outpoint_dict()
                for tx_input in self.inputs
            ],

            "outputs": [
                tx_output.to_dict()
                for tx_output in self.outputs
            ],

            "timestamp": self.timestamp,

            "signing_input_index": input_index,

            "public_key":
                self.inputs[input_index].public_key,
        }

    def signing_bytes(
        self,
        input_index: int,
    ) -> bytes:

        return serialize(
            self.signing_dict(input_index)
        )

    def sign_input(
        self,
        input_index: int,
        private_key: SigningKey,
    ) -> None:

        if (
            input_index < 0
            or input_index >= len(self.inputs)
        ):
            raise IndexError(
                "input_index out of range"
            )

        public_key = get_public_key(
            private_key
        )

        self.inputs[
            input_index
        ].public_key = public_key_to_hex(
            public_key
        )

        message = self.signing_bytes(
            input_index
        )

        signature = sign_message(
            private_key,
            message,
        )

        self.inputs[
            input_index
        ].signature = signature.hex()

    def txid(self) -> str:
        transaction_bytes = serialize(
            self.to_dict(
                include_signatures=True
            )
        )

        return sha256_hex(
            transaction_bytes
        )
