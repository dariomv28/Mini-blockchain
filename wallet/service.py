"""Wallet operations use public Node snapshots and durable retry records."""

import asyncio
import hashlib
import time

from api.errors import APIError
from crypto.hash import serialize
from storage.codec import decode_transaction, encode_transaction
from wallet.coin_selection import InsufficientBalanceError, select_utxos
from wallet.transaction_builder import TransactionWorkLimitError, build_signed_transaction


MAX_WALLET_INPUTS = 100


class WalletService:
    def __init__(self, database, node, keystore):
        self.database = database
        self.node = node
        self.keystore = keystore
        self._locks = {}
        self._tasks = set()
        # Bound CPU work across users; tracked sends keep this slot until the
        # actual worker finishes even if its HTTP caller disconnects.
        self._build_jobs = asyncio.Semaphore(2)

    def _wallet(self, user_id):
        row = self.database.wallet(user_id)
        if row is None:
            raise APIError(404, "WALLET_NOT_FOUND", "Wallet was not found")
        return row

    async def get_wallet_summary(self, user_id):
        wallet = self._wallet(user_id)
        view = await self.node.get_wallet_state(wallet["address"])
        reserved = {(i.previous_tx_id, i.output_index) for tx in view["pending"] for i in tx.inputs}
        available = {point: out for point, out in view["utxos"].items() if point not in reserved}
        relevant = [tx for tx in view["pending"] if any(i.public_key.casefold() == wallet["public_key"] for i in tx.inputs)
                    or any(o.recipient_address == wallet["address"] for o in tx.outputs)]
        pending_incoming = 0
        for tx in relevant:
            txid = tx.txid()
            pending_incoming += sum(o.amount for index, o in enumerate(tx.outputs)
                                    if o.recipient_address == wallet["address"] and (txid, index) not in reserved)
        return {"address": wallet["address"], "public_key": wallet["public_key"],
                "confirmed_balance": view["confirmed_balance"], "available_balance": sum(o.amount for o in available.values()),
                "pending_outgoing": sum(o.amount for p, o in view["utxos"].items() if p in reserved),
                "pending_incoming": pending_incoming,
                "pending_count": len(relevant)}

    async def history(self, user_id, start=0, limit=20):
        return await self.node.get_wallet_history(self._wallet(user_id)["address"], start=start, limit=limit)

    async def send(self, user_id, recipient, amount, fee, idempotency_key):
        # A browser disconnect must not abandon an accepted transaction before
        # persisting its result. Shutdown waits for these tracked operations.
        task = asyncio.create_task(self._send(user_id, recipient, amount, fee, idempotency_key))
        self._tasks.add(task)
        def finished(done):
            self._tasks.discard(done)
            if not done.cancelled():
                done.exception()
        task.add_done_callback(finished)
        return await asyncio.shield(task)

    async def close(self):
        if self._tasks:
            await asyncio.gather(*list(self._tasks), return_exceptions=True)

    def _prepare_transaction(self, wallet, view, recipient, amount, fee, max_bytes):
        """CPU-only worker: never access AppDatabase or mutable Node state."""
        reserved = {(i.previous_tx_id, i.output_index) for pending in view["pending"] for i in pending.inputs}
        available = {point: out for point, out in view["utxos"].items() if point not in reserved}
        selection = select_utxos(available, amount=amount, fee=fee)
        if len(selection.selected) > MAX_WALLET_INPUTS:
            raise TransactionWorkLimitError("Wallet sends support at most 100 inputs")
        private_key = self.keystore.decrypt_private_key(wallet["encrypted_private_key"], wallet["key_version"])
        try:
            tx = build_signed_transaction(selected_utxos=selection.selected, sender_address=wallet["address"],
                                          recipient_address=recipient, amount=amount, fee=fee, private_key=private_key,
                                          max_bytes=max_bytes)
        finally:
            del private_key
        data = encode_transaction(tx)
        if len(data) > max_bytes:
            raise TransactionWorkLimitError("Transaction exceeds node item limit")
        return tx, data

    async def _send(self, user_id, recipient, amount, fee, key):
        lock = self._locks.setdefault(user_id, asyncio.Lock())
        async with lock:
            fingerprint = hashlib.sha256(serialize({"recipient_address": recipient, "amount": amount, "fee": fee})).hexdigest()
            record = self.database.idempotency(user_id, key)
            if record is not None:
                if record["request_fingerprint"] != fingerprint:
                    raise APIError(409, "IDEMPOTENCY_CONFLICT", "Idempotency key was already used with another request")
                if record["state"] == "accepted":
                    return {"txid": record["result_txid"], "status": "pending"}
                if record["state"] == "rejected":
                    raise APIError(409, "TRANSACTION_CONFLICT", "Transaction was rejected; use a new intent and idempotency key")
            else:
                self.database.execute(
                    "INSERT INTO idempotency_records(user_id,idempotency_key,operation,request_fingerprint,state,created_at) VALUES(?,?,'wallet.send',?,'reserved',?)",
                    (user_id, key, fingerprint, int(time.time())),
                )
            if record is not None and record["transaction_data"] is not None:
                tx = decode_transaction(record["transaction_data"])
            else:
                try:
                    wallet = dict(self._wallet(user_id))
                    view = await self.node.get_wallet_state(wallet["address"])
                    async with self._build_jobs:
                        tx, data = await asyncio.to_thread(self._prepare_transaction, wallet, view, recipient,
                                                         amount, fee, self.node.config.max_item_bytes)
                    # Persist exact signed bytes BEFORE crossing the Node boundary.
                    self.database.execute(
                        "UPDATE idempotency_records SET transaction_data=?,result_txid=?,state='prepared' WHERE user_id=? AND idempotency_key=? AND operation='wallet.send'",
                        (data, tx.txid(), user_id, key),
                    )
                except BaseException as exc:
                    self.database.execute("DELETE FROM idempotency_records WHERE user_id=? AND idempotency_key=? AND state='reserved' AND operation='wallet.send'", (user_id, key))
                    if isinstance(exc, InsufficientBalanceError):
                        raise APIError(409, "INSUFFICIENT_BALANCE", "Insufficient available balance") from None
                    if isinstance(exc, TransactionWorkLimitError):
                        raise APIError(413, "TRANSACTION_TOO_LARGE", str(exc)) from None
                    raise
            match = await self.node.find_transaction(tx.txid())
            accepted = match is not None or await self.node.submit_transaction(tx)
            if not accepted:
                # Another submit could have won while this command was queued.
                accepted = await self.node.find_transaction(tx.txid()) is not None
            self.database.execute(
                "UPDATE idempotency_records SET state=? WHERE user_id=? AND idempotency_key=? AND operation='wallet.send'",
                ("accepted" if accepted else "rejected", user_id, key),
            )
            if not accepted:
                raise APIError(409, "TRANSACTION_CONFLICT", "Transaction was rejected by node admission rules")
            return {"txid": tx.txid(), "status": "pending"}
