"""Serializers translating core blockchain domain objects to API dictionaries."""

from __future__ import annotations

from typing import Any
from blockchain.block import Block
from transaction.transaction import Transaction
from transaction.tx_input import TxInput
from transaction.tx_output import TxOutput
from api.schemas.transaction import TransactionSubmitRequest


def transaction_to_response(tx: Transaction) -> dict[str, Any]:
    return {
        "txid": tx.txid(),
        "version": tx.version,
        "timestamp": tx.timestamp,
        "inputs": [
            {
                "previous_tx_id": inp.previous_tx_id,
                "output_index": inp.output_index,
                "public_key": inp.public_key,
                "signature": inp.signature,
            }
            for inp in tx.inputs
        ],
        "outputs": [
            {
                "amount": out.amount,
                "recipient_address": out.recipient_address,
            }
            for out in tx.outputs
        ],
        "is_coinbase": len(tx.inputs) == 0,
    }


def block_to_response(block: Block, height: int | None = None) -> dict[str, Any]:
    return {
        "height": height,
        "hash": block.hash(),
        "header": {
            "version": block.version,
            "previous_block_hash": block.previous_block_hash,
            "merkle_root": block.merkle_root,
            "timestamp": block.timestamp,
            "difficulty": block.difficulty,
            "nonce": block.nonce,
        },
        "transaction_count": len(block.transactions),
        "transactions": [transaction_to_response(tx) for tx in block.transactions],
    }


def utxo_to_response(outpoint: tuple[str, int], output: TxOutput) -> dict[str, Any]:
    return {
        "txid": outpoint[0],
        "output_index": outpoint[1],
        "amount": output.amount,
        "recipient_address": output.recipient_address,
    }


def request_to_transaction(req: TransactionSubmitRequest) -> Transaction:
    inputs = [
        TxInput(
            previous_tx_id=i.previous_tx_id,
            output_index=i.output_index,
            public_key=i.public_key,
            signature=i.signature,
        )
        for i in req.inputs
    ]
    outputs = [
        TxOutput(
            amount=o.amount,
            recipient_address=o.recipient_address,
        )
        for o in req.outputs
    ]
    return Transaction(
        inputs=inputs,
        outputs=outputs,
        timestamp=req.timestamp,
        version=req.version,
    )


def request_to_block(req: Any) -> Block:
    transactions = []
    for tx_req in req.transactions:
        inputs = [
            TxInput(
                previous_tx_id=i.previous_tx_id,
                output_index=i.output_index,
                public_key=i.public_key,
                signature=i.signature,
            )
            for i in tx_req.inputs
        ]
        outputs = [
            TxOutput(
                amount=o.amount,
                recipient_address=o.recipient_address,
            )
            for o in tx_req.outputs
        ]
        transactions.append(
            Transaction(
                inputs=inputs,
                outputs=outputs,
                timestamp=tx_req.timestamp,
                version=tx_req.version,
            )
        )

    block = Block(
        transactions=transactions,
        previous_block_hash=req.header.previous_block_hash,
        timestamp=req.header.timestamp,
        version=req.header.version,
        difficulty=req.header.difficulty,
        nonce=req.header.nonce,
    )

    if block.merkle_root != req.header.merkle_root:
        from api.errors import APIError
        from fastapi import status
        raise APIError(
            status.HTTP_400_BAD_REQUEST,
            "INVALID_MERKLE_ROOT",
            "Declared header Merkle root does not match block transactions",
        )

    return block

