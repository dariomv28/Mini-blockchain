"""Explorer service providing in-memory ChainView index and query operations (Phase 14)."""

from __future__ import annotations

import asyncio
from collections import defaultdict
from typing import Any

from crypto.address import validate_address
from network.node import Node
from blockchain.block import Block
from transaction.transaction import Transaction
from storage.codec import encode_block, encode_transaction
from api.errors import APIError
from fastapi import status
from api.schemas.explorer import (
    EnrichedTransactionResponse,
    EnrichedTxInput,
    EnrichedTxOutput,
    ExplorerAddressDetailResponse,
    ExplorerAddressHistoryItem,
    ExplorerBlockDetailResponse,
    ExplorerBlockListItem,
    ExplorerBlocksResponse,
    ExplorerMempoolEntryItem,
    ExplorerMempoolResponse,
    ExplorerSearchResponse,
    ExplorerStatsResponse,
    ExplorerUTXOItem,
)


class ChainView:
    """Consistent in-memory snapshot index of the active blockchain."""

    def __init__(self, tip_height: int, tip_hash: str) -> None:
        self.tip_height = tip_height
        self.tip_hash = tip_hash
        self.blocks_by_height: dict[int, Block] = {}
        self.blocks_by_hash: dict[str, tuple[int, Block]] = {}
        self.block_sizes: dict[int, int] = {}
        self.tx_by_id: dict[str, tuple[int, str, Transaction]] = {}
        self.tx_fees: dict[str, int] = {}
        self.tx_sizes: dict[str, int] = {}
        self.outputs_by_outpoint: dict[tuple[str, int], Any] = {}
        self.address_history: dict[str, list[dict[str, Any]]] = defaultdict(list)
        self.total_confirmed_transactions: int = 0

    def populate(self, blocks: list[Block]) -> None:
        # Pass 1: Index blocks and all transaction outputs
        for height, block in enumerate(blocks):
            bhash = block.hash()
            self.blocks_by_height[height] = block
            self.blocks_by_hash[bhash] = (height, block)
            try:
                self.block_sizes[height] = len(encode_block(block))
            except Exception:
                self.block_sizes[height] = 0

            for tx in block.transactions:
                txid = tx.txid()
                self.total_confirmed_transactions += 1
                self.tx_by_id[txid] = (height, bhash, tx)
                try:
                    self.tx_sizes[txid] = len(encode_transaction(tx))
                except Exception:
                    self.tx_sizes[txid] = 0

                for idx, out in enumerate(tx.outputs):
                    self.outputs_by_outpoint[(txid, idx)] = out

        # Pass 2: Calculate transaction fees, inputs, and build address history
        for height, block in enumerate(blocks):
            bhash = block.hash()
            for tx in block.transactions:
                txid = tx.txid()
                is_coinbase = len(tx.inputs) == 0

                if is_coinbase:
                    self.tx_fees[txid] = 0
                    coinbase_by_addr: dict[str, int] = defaultdict(int)
                    for out in tx.outputs:
                        coinbase_by_addr[out.recipient_address] += out.amount
                    for recipient, mined_amt in coinbase_by_addr.items():
                        self.address_history[recipient].append({
                            "txid": txid,
                            "block_height": height,
                            "timestamp": tx.timestamp,
                            "status": "confirmed",
                            "direction": "mined",
                            "amount": mined_amt,
                            "fee": 0,
                        })
                else:
                    in_amount = 0
                    sender_addresses: set[str] = set()
                    for inp in tx.inputs:
                        prev = self.outputs_by_outpoint.get((inp.previous_tx_id, inp.output_index))
                        if prev is not None:
                            in_amount += prev.amount
                            sender_addresses.add(prev.recipient_address)

                    out_amount = sum(out.amount for out in tx.outputs)
                    fee = max(0, in_amount - out_amount)
                    self.tx_fees[txid] = fee

                    for sender in sender_addresses:
                        sent_amount = sum(out.amount for out in tx.outputs if out.recipient_address != sender)
                        self.address_history[sender].append({
                            "txid": txid,
                            "block_height": height,
                            "timestamp": tx.timestamp,
                            "status": "confirmed",
                            "direction": "sent",
                            "amount": sent_amount,
                            "fee": fee,
                        })

                    received_by_addr: dict[str, int] = defaultdict(int)
                    for out in tx.outputs:
                        if out.recipient_address not in sender_addresses:
                            received_by_addr[out.recipient_address] += out.amount

                    for recipient, rec_amt in received_by_addr.items():
                        self.address_history[recipient].append({
                            "txid": txid,
                            "block_height": height,
                            "timestamp": tx.timestamp,
                            "status": "confirmed",
                            "direction": "received",
                            "amount": rec_amt,
                            "fee": fee,
                        })

        # Sort each address history descending by block_height and timestamp
        for records in self.address_history.values():
            records.sort(key=lambda r: (r.get("block_height") or 0, r.get("timestamp") or 0), reverse=True)


class ExplorerService:
    """Service handling Blockchain Explorer domain queries with in-memory caching."""

    def __init__(self) -> None:
        self._cached_chain_view: ChainView | None = None
        self._lock = asyncio.Lock()

    async def get_chain_view(self, node: Node, force_refresh: bool = False) -> ChainView:
        latest = await node.get_latest_block_info()
        if latest is None:
            return ChainView(0, "")

        tip_hash = latest["block"].hash()
        tip_height = latest["height"]

        if not force_refresh and self._cached_chain_view is not None and self._cached_chain_view.tip_hash == tip_hash:
            return self._cached_chain_view

        async with self._lock:
            # Double-check inside lock
            if not force_refresh and self._cached_chain_view is not None and self._cached_chain_view.tip_hash == tip_hash:
                return self._cached_chain_view

            batch_size = 100
            total_needed = tip_height + 1
            blocks: list[Block] = []
            start = 0

            while start < total_needed:
                limit = min(batch_size, total_needed - start)
                batch = await node.get_blocks(start, limit)
                if not batch:
                    break
                blocks.extend(batch)
                start += len(batch)

            if len(blocks) != total_needed:
                # Incomplete snapshot retrieved; do not cache partial/empty state
                if self._cached_chain_view is not None:
                    return self._cached_chain_view
                raise APIError(
                    status.HTTP_503_SERVICE_UNAVAILABLE,
                    "CHAIN_SNAPSHOT_INCOMPLETE",
                    f"Failed to fetch complete chain snapshot ({len(blocks)}/{total_needed} blocks)",
                )

            new_view = ChainView(tip_height, tip_hash)
            new_view.populate(blocks)
            self._cached_chain_view = new_view
            return new_view

    def enrich_transaction(
        self,
        tx: Transaction,
        chain_view: ChainView,
        status_str: str,
        block_height: int | None = None,
        block_hash: str | None = None,
        known_fee: int | None = None,
        known_size: int | None = None,
    ) -> EnrichedTransactionResponse:
        is_coinbase = len(tx.inputs) == 0
        txid = tx.txid()

        enriched_inputs: list[EnrichedTxInput] = []
        total_in = 0
        for inp in tx.inputs:
            prev = chain_view.outputs_by_outpoint.get((inp.previous_tx_id, inp.output_index))
            source_addr = prev.recipient_address if prev else None
            amount = prev.amount if prev else None
            if amount is not None:
                total_in += amount
            enriched_inputs.append(
                EnrichedTxInput(
                    previous_tx_id=inp.previous_tx_id,
                    output_index=inp.output_index,
                    public_key=inp.public_key,
                    signature=inp.signature,
                    source_address=source_addr,
                    amount=amount,
                )
            )

        enriched_outputs: list[EnrichedTxOutput] = [
            EnrichedTxOutput(
                index=idx,
                recipient_address=out.recipient_address,
                amount=out.amount,
            )
            for idx, out in enumerate(tx.outputs)
        ]

        if known_fee is not None:
            fee = known_fee
        elif is_coinbase:
            fee = 0
        elif txid in chain_view.tx_fees:
            fee = chain_view.tx_fees[txid]
        else:
            total_out = sum(out.amount for out in tx.outputs)
            fee = max(0, total_in - total_out)

        if known_size is not None:
            size_bytes = known_size
        elif txid in chain_view.tx_sizes:
            size_bytes = chain_view.tx_sizes[txid]
        else:
            try:
                size_bytes = len(encode_transaction(tx))
            except Exception:
                size_bytes = 0

        return EnrichedTransactionResponse(
            txid=txid,
            status=status_str,
            block_height=block_height,
            block_hash=block_hash,
            timestamp=tx.timestamp,
            version=tx.version,
            is_coinbase=is_coinbase,
            inputs=enriched_inputs,
            outputs=enriched_outputs,
            fee=fee,
            size_bytes=size_bytes,
        )

    async def get_stats(self, node: Node) -> ExplorerStatsResponse:
        chain_view = await self.get_chain_view(node)
        status_info = await node.get_status()
        pending_entries = await node.get_pending_entries()

        peers = status_info.get("peers", [])
        peer_count = len(peers) if isinstance(peers, list) else status_info.get("peer_count", 0)

        return ExplorerStatsResponse(
            height=chain_view.tip_height,
            tip_hash=chain_view.tip_hash,
            mempool_count=len(pending_entries),
            peer_count=peer_count,
            total_confirmed_transactions=chain_view.total_confirmed_transactions,
        )

    async def get_latest_blocks(
        self,
        node: Node,
        limit: int = 10,
        offset: int = 0,
    ) -> ExplorerBlocksResponse:
        if limit < 1 or limit > 50:
            raise APIError(status.HTTP_400_BAD_REQUEST, "INVALID_PAGINATION", "limit must be between 1 and 50")
        if offset < 0:
            raise APIError(status.HTTP_400_BAD_REQUEST, "INVALID_PAGINATION", "offset must be >= 0")

        chain_view = await self.get_chain_view(node)
        total_blocks = chain_view.tip_height + 1 if chain_view.blocks_by_height else 0

        # Descending from tip_height
        items: list[ExplorerBlockListItem] = []
        for i in range(offset, min(offset + limit, total_blocks)):
            h = chain_view.tip_height - i
            if h in chain_view.blocks_by_height:
                blk = chain_view.blocks_by_height[h]
                miner_addr = None
                if blk.transactions and len(blk.transactions[0].inputs) == 0:
                    if blk.transactions[0].outputs:
                        miner_addr = blk.transactions[0].outputs[0].recipient_address

                items.append(
                    ExplorerBlockListItem(
                        height=h,
                        hash=blk.hash(),
                        previous_block_hash=blk.previous_block_hash,
                        timestamp=blk.timestamp,
                        transaction_count=len(blk.transactions),
                        size_bytes=chain_view.block_sizes.get(h, 0),
                        miner_address=miner_addr,
                        difficulty=blk.difficulty,
                        nonce=blk.nonce,
                    )
                )

        return ExplorerBlocksResponse(
            total_blocks=total_blocks,
            blocks=items,
            limit=limit,
            offset=offset,
        )

    async def get_block_by_height(self, node: Node, height: int) -> ExplorerBlockDetailResponse:
        if height < 0:
            raise APIError(status.HTTP_400_BAD_REQUEST, "INVALID_HEIGHT", "Block height must be non-negative")

        chain_view = await self.get_chain_view(node)
        if height not in chain_view.blocks_by_height:
            raise APIError(status.HTTP_404_NOT_FOUND, "BLOCK_NOT_FOUND", f"Block at height {height} does not exist")

        block = chain_view.blocks_by_height[height]
        return self._format_block_detail(block, height, chain_view)

    async def get_block_by_hash(self, node: Node, block_hash: str) -> ExplorerBlockDetailResponse:
        valid_hash = block_hash.strip().lower()
        if len(valid_hash) != 64 or not all(c in "0123456789abcdef" for c in valid_hash):
            raise APIError(status.HTTP_400_BAD_REQUEST, "INVALID_HASH", "Block hash must be a 64-character hexadecimal string")

        chain_view = await self.get_chain_view(node)
        if valid_hash not in chain_view.blocks_by_hash:
            raise APIError(status.HTTP_404_NOT_FOUND, "BLOCK_NOT_FOUND", f"Block with hash '{valid_hash}' was not found")

        height, block = chain_view.blocks_by_hash[valid_hash]
        return self._format_block_detail(block, height, chain_view)

    def _format_block_detail(
        self,
        block: Block,
        height: int,
        chain_view: ChainView,
    ) -> ExplorerBlockDetailResponse:
        bhash = block.hash()
        miner_addr = None
        total_fees = 0
        total_output_amount = 0
        enriched_txs: list[EnrichedTransactionResponse] = []

        for idx, tx in enumerate(block.transactions):
            tx_res = self.enrich_transaction(
                tx,
                chain_view,
                status_str="confirmed",
                block_height=height,
                block_hash=bhash,
            )
            enriched_txs.append(tx_res)
            if idx == 0 and tx_res.is_coinbase:
                if tx.outputs:
                    miner_addr = tx.outputs[0].recipient_address
            else:
                total_fees += tx_res.fee

            total_output_amount += sum(o.amount for o in tx.outputs)

        return ExplorerBlockDetailResponse(
            height=height,
            hash=bhash,
            version=block.version,
            previous_block_hash=block.previous_block_hash,
            merkle_root=block.merkle_root,
            timestamp=block.timestamp,
            difficulty=block.difficulty,
            nonce=block.nonce,
            transaction_count=len(block.transactions),
            size_bytes=chain_view.block_sizes.get(height, 0),
            miner_address=miner_addr,
            total_fees=total_fees,
            total_output_amount=total_output_amount,
            transactions=enriched_txs,
        )

    async def get_transaction(self, node: Node, txid: str) -> EnrichedTransactionResponse:
        valid_txid = txid.strip().lower()
        if len(valid_txid) != 64 or not all(c in "0123456789abcdef" for c in valid_txid):
            raise APIError(status.HTTP_400_BAD_REQUEST, "INVALID_TXID", "Transaction ID must be a 64-character hexadecimal string")

        chain_view = await self.get_chain_view(node)

        # 1. Check mempool pending entries first
        entries = await node.get_pending_entries()
        for entry in entries:
            ptx = entry["transaction"]
            if ptx.txid() == valid_txid:
                return self.enrich_transaction(
                    ptx,
                    chain_view,
                    status_str="pending",
                    known_fee=entry.get("fee"),
                    known_size=entry.get("size_bytes"),
                )

        # 2. Check confirmed transactions in chain_view
        if valid_txid in chain_view.tx_by_id:
            height, bhash, ctx = chain_view.tx_by_id[valid_txid]
            return self.enrich_transaction(
                ctx,
                chain_view,
                status_str="confirmed",
                block_height=height,
                block_hash=bhash,
            )

        # 3. If missing, check if block was mined during the query
        found_block = await node.find_transaction(valid_txid)
        latest = await node.get_latest_block_info()
        latest_tip = latest["block"].hash() if latest else ""

        if found_block is not None or (latest_tip and latest_tip != chain_view.tip_hash):
            refreshed_view = await self.get_chain_view(node, force_refresh=True)
            if valid_txid in refreshed_view.tx_by_id:
                height, bhash, ctx = refreshed_view.tx_by_id[valid_txid]
                return self.enrich_transaction(
                    ctx,
                    refreshed_view,
                    status_str="confirmed",
                    block_height=height,
                    block_hash=bhash,
                )

        raise APIError(status.HTTP_404_NOT_FOUND, "TRANSACTION_NOT_FOUND", f"Transaction '{valid_txid}' was not found in mempool or blockchain")

    async def get_address_detail(
        self,
        node: Node,
        address: str,
        limit: int = 20,
        offset: int = 0,
    ) -> ExplorerAddressDetailResponse:
        addr = address.strip()
        if not validate_address(addr):
            raise APIError(status.HTTP_400_BAD_REQUEST, "INVALID_ADDRESS", f"'{addr}' is not a valid PYC address")
        if limit < 1 or limit > 100:
            raise APIError(status.HTTP_400_BAD_REQUEST, "INVALID_PAGINATION", "limit must be between 1 and 100")
        if offset < 0:
            raise APIError(status.HTTP_400_BAD_REQUEST, "INVALID_PAGINATION", "offset must be >= 0")

        chain_view = await self.get_chain_view(node)
        addr_info = await node.get_address_info(addr)

        # Ensure consistent state if tip changed while querying address info
        latest = await node.get_latest_block_info()
        latest_tip = latest["block"].hash() if latest else ""
        if latest_tip and latest_tip != chain_view.tip_hash:
            chain_view = await self.get_chain_view(node, force_refresh=True)
            addr_info = await node.get_address_info(addr)

        # Build UTXO list
        utxos: list[ExplorerUTXOItem] = [
            ExplorerUTXOItem(
                txid=outpoint[0],
                output_index=outpoint[1],
                amount=output.amount,
                recipient_address=output.recipient_address,
            )
            for outpoint, output in addr_info["utxos"].items()
        ]

        # Scan mempool for pending transactions involving address
        pending_history: list[dict[str, Any]] = []
        entries = await node.get_pending_entries()
        for entry in entries:
            ptx = entry["transaction"]
            txid = ptx.txid()
            fee = entry.get("fee", 0)

            # Check if address is sender
            is_sender = False
            for inp in ptx.inputs:
                prev = chain_view.outputs_by_outpoint.get((inp.previous_tx_id, inp.output_index))
                if prev and prev.recipient_address == addr:
                    is_sender = True
                    break

            if is_sender:
                sent_amt = sum(out.amount for out in ptx.outputs if out.recipient_address != addr)
                pending_history.append({
                    "txid": txid,
                    "block_height": None,
                    "timestamp": ptx.timestamp,
                    "status": "pending",
                    "direction": "sent",
                    "amount": sent_amt,
                    "fee": fee,
                })
            else:
                received_amt = sum(out.amount for out in ptx.outputs if out.recipient_address == addr)
                if received_amt > 0:
                    pending_history.append({
                        "txid": txid,
                        "block_height": None,
                        "timestamp": ptx.timestamp,
                        "status": "pending",
                        "direction": "received",
                        "amount": received_amt,
                        "fee": fee,
                    })

        confirmed_history = chain_view.address_history.get(addr, [])
        all_history = pending_history + confirmed_history
        total_txs = len(all_history)

        paginated_history = [
            ExplorerAddressHistoryItem(
                txid=item["txid"],
                block_height=item.get("block_height"),
                timestamp=item["timestamp"],
                status=item["status"],
                direction=item["direction"],
                amount=item["amount"],
                fee=item.get("fee", 0),
            )
            for item in all_history[offset : offset + limit]
        ]

        return ExplorerAddressDetailResponse(
            address=addr,
            confirmed_balance=addr_info["confirmed_balance"],
            utxo_count=addr_info["utxo_count"],
            utxos=utxos,
            total_transactions=total_txs,
            transactions=paginated_history,
            limit=limit,
            offset=offset,
        )

    async def get_mempool(self, node: Node) -> ExplorerMempoolResponse:
        entries = await node.get_pending_entries()
        total_bytes = sum(e.get("size_bytes", 0) for e in entries)

        items: list[ExplorerMempoolEntryItem] = []
        for e in sorted(entries, key=lambda x: x["transaction"].timestamp, reverse=True):
            tx = e["transaction"]
            items.append(
                ExplorerMempoolEntryItem(
                    txid=tx.txid(),
                    timestamp=tx.timestamp,
                    inputs_count=len(tx.inputs),
                    outputs_count=len(tx.outputs),
                    fee=e.get("fee", 0),
                    size_bytes=e.get("size_bytes", 0),
                    status="pending",
                )
            )

        return ExplorerMempoolResponse(
            count=len(items),
            total_bytes=total_bytes,
            transactions=items,
        )

    async def search(self, node: Node, query: str) -> ExplorerSearchResponse:
        q = query.strip()
        if not q or len(q) > 100:
            return ExplorerSearchResponse(query=q, result_type="not_found")

        chain_view = await self.get_chain_view(node)

        # 1. Check Address format
        if q.startswith("PYC_") and validate_address(q):
            return ExplorerSearchResponse(
                query=q,
                result_type="address",
                target_url=f"/explorer/address/{q}",
                payload={"address": q},
            )

        # 2. Check Decimal Block Height
        if q.isascii() and q.isdigit():
            try:
                h = int(q)
                if h in chain_view.blocks_by_height:
                    blk = chain_view.blocks_by_height[h]
                    return ExplorerSearchResponse(
                        query=q,
                        result_type="block",
                        target_url=f"/explorer/block/{h}",
                        payload={"height": h, "hash": blk.hash()},
                    )
            except (ValueError, OverflowError):
                pass

        # 3. Check 64-char Hex Hash
        if len(q) == 64 and all(c in "0123456789abcdefABCDEF" for c in q):
            hex_q = q.lower()
            # Try block hash first
            if hex_q in chain_view.blocks_by_hash:
                h, blk = chain_view.blocks_by_hash[hex_q]
                return ExplorerSearchResponse(
                    query=q,
                    result_type="block",
                    target_url=f"/explorer/block/{hex_q}",
                    payload={"height": h, "hash": hex_q},
                )
            # Try confirmed transaction
            if hex_q in chain_view.tx_by_id:
                h, bhash, tx = chain_view.tx_by_id[hex_q]
                return ExplorerSearchResponse(
                    query=q,
                    result_type="transaction",
                    target_url=f"/explorer/tx/{hex_q}",
                    payload={"txid": hex_q, "status": "confirmed", "height": h},
                )
            # Try mempool pending transaction
            entries = await node.get_pending_entries()
            for entry in entries:
                if entry["transaction"].txid() == hex_q:
                    return ExplorerSearchResponse(
                        query=q,
                        result_type="transaction",
                        target_url=f"/explorer/tx/{hex_q}",
                        payload={"txid": hex_q, "status": "pending"},
                    )

        return ExplorerSearchResponse(query=q, result_type="not_found")


# Global singleton instance of ExplorerService
explorer_service = ExplorerService()
