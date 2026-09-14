"""Mining service: background worker execution, template building, and job lifecycle management."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
import logging
import threading
import time
from typing import Any
import uuid

from blockchain.block import Block
from mining.miner import mine_block_with_progress
from network.node import Node
from api.config import ApiConfig
from api.errors import APIError
from api.websocket.manager import WebSocketManager

logger = logging.getLogger("pychain.api.mining")


@dataclass
class MiningJob:
    id: str
    user_id: int
    miner_address: str
    status: str  # QUEUED, MINING, FOUND, ACCEPTED, STALE, FAILED, CANCELLED
    created_at: float
    template_height: int
    previous_hash: str
    transaction_count: int
    difficulty: int
    subsidy: int = 50
    fees: int = 0
    total_reward: int = 50
    started_at: float | None = None
    finished_at: float | None = None
    result_hash: str | None = None
    nonce: int | None = None
    hashes_tried: int = 0
    current_hash: str | None = None
    elapsed_seconds: float = 0.0
    accepted: bool | None = None
    error: str | None = None
    stop_event: threading.Event = field(default_factory=threading.Event)

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "status": self.status,
            "miner_address": self.miner_address,
            "created_at": self.created_at,
            "started_at": self.started_at,
            "finished_at": self.finished_at,
            "template_height": self.template_height,
            "previous_hash": self.previous_hash,
            "transaction_count": self.transaction_count,
            "difficulty": self.difficulty,
            "result_hash": self.result_hash,
            "nonce": self.nonce,
            "hashes_tried": self.hashes_tried,
            "current_hash": self.current_hash,
            "elapsed_seconds": round(self.elapsed_seconds, 2),
            "accepted": self.accepted,
            "error": self.error,
            "subsidy": self.subsidy,
            "fees": self.fees,
            "total_reward": self.total_reward,
        }


class MiningService:
    def __init__(self, node: Node, ws_manager: WebSocketManager | None, config: ApiConfig):
        self.node = node
        self.ws_manager = ws_manager
        self.config = config
        self._jobs: dict[str, MiningJob] = {}
        self._active_job_id: str | None = None
        self._lock = asyncio.Lock()
        self._worker_task: asyncio.Task | None = None
        self._closed = False

    async def _safe_broadcast(self, message: dict[str, Any]) -> None:
        if self.ws_manager is not None:
            try:
                await self.ws_manager.broadcast(message)
            except Exception as exc:
                logger.debug("Failed broadcasting mining event: %s", exc)

    def _schedule_broadcast(self, message: dict[str, Any]) -> None:
        if not self._closed:
            asyncio.create_task(self._safe_broadcast(message))

    async def build_candidate_template(
        self,
        miner_address: str,
        max_transactions: int = 100,
        max_bytes: int = 100_000,
    ) -> dict[str, Any]:
        bounded_txs = min(max(0, max_transactions), self.config.mining_max_transactions)
        bounded_bytes = min(max(1000, max_bytes), self.config.mining_max_bytes)

        template = await self.node.create_mempool_block_template(
            miner_address,
            max_transactions=bounded_txs,
            max_bytes=bounded_bytes,
        )

        coinbase_tx = template.transactions[0] if template.transactions else None
        coinbase_output_amount = coinbase_tx.outputs[0].amount if (coinbase_tx and coinbase_tx.outputs) else 50
        fees = max(0, coinbase_output_amount - 50)
        status_data = await self.node.get_status()

        return {
            "previous_block_hash": template.previous_block_hash,
            "merkle_root": template.merkle_root,
            "difficulty": template.difficulty,
            "nonce": template.nonce,
            "template_height": status_data["height"] + 1,
            "timestamp": template.timestamp,
            "miner_address": miner_address,
            "transactions": [tx.to_dict() for tx in template.transactions],
            "transaction_count": len(template.transactions),
            "subsidy": 50,
            "fees": fees,
            "total_reward": coinbase_output_amount,
        }

    async def create_job(
        self,
        user_id: int,
        miner_address: str,
        max_transactions: int = 100,
        max_bytes: int = 100_000,
        max_nonce: int | None = None,
    ) -> MiningJob:
        async with self._lock:
            if self._closed:
                raise APIError(503, "SERVICE_UNAVAILABLE", "Mining service is closed")

            # Check single active job limit
            if self._active_job_id is not None:
                active = self._jobs.get(self._active_job_id)
                if active and active.status in ("QUEUED", "MINING"):
                    raise APIError(409, "MINING_BUSY", "A mining job is already running on this node")

            bounded_nonce = min(
                max(1, max_nonce or self.config.mining_max_nonce),
                self.config.mining_max_nonce,
            )
            bounded_txs = min(max(0, max_transactions), self.config.mining_max_transactions)
            bounded_bytes = min(max(1000, max_bytes), self.config.mining_max_bytes)

            template = await self.node.create_mempool_block_template(
                miner_address,
                max_transactions=bounded_txs,
                max_bytes=bounded_bytes,
            )

            coinbase_tx = template.transactions[0] if template.transactions else None
            coinbase_output_amount = coinbase_tx.outputs[0].amount if (coinbase_tx and coinbase_tx.outputs) else 50
            fees = max(0, coinbase_output_amount - 50)
            status_data = await self.node.get_status()

            job_id = uuid.uuid4().hex
            job = MiningJob(
                id=job_id,
                user_id=user_id,
                miner_address=miner_address,
                status="QUEUED",
                created_at=time.time(),
                template_height=status_data["height"] + 1,
                previous_hash=template.previous_block_hash,
                transaction_count=len(template.transactions),
                difficulty=template.difficulty,
                subsidy=50,
                fees=fees,
                total_reward=coinbase_output_amount,
            )

            self._jobs[job_id] = job
            self._active_job_id = job_id
            self._worker_task = asyncio.create_task(
                self._run_mining(job, template, bounded_nonce),
                name=f"mining-worker-{job_id}",
            )
            return job

    async def _run_mining(self, job: MiningJob, template: Block, max_nonce: int) -> None:
        job.status = "MINING"
        job.started_at = time.time()

        await self._safe_broadcast({
            "type": "mining_started",
            "payload": {
                "job_id": job.id,
                "miner_address": job.miner_address,
                "height": job.template_height,
                "difficulty": job.difficulty,
                "transaction_count": job.transaction_count,
            },
        })

        loop = asyncio.get_running_loop()
        last_progress_time = 0.0

        def on_progress(p: dict[str, Any]) -> None:
            nonlocal last_progress_time
            job.nonce = p["nonce"]
            job.current_hash = p["hash"]
            job.hashes_tried = p["hashes_tried"]
            now = time.time()
            job.elapsed_seconds = now - (job.started_at or now)

            # Throttle progress broadcasts to at most once every 500ms
            if now - last_progress_time >= 0.5:
                last_progress_time = now
                payload = {
                    "job_id": job.id,
                    "nonce": p["nonce"],
                    "hashes_tried": p["hashes_tried"],
                    "hash": p["hash"],
                    "elapsed_seconds": round(job.elapsed_seconds, 2),
                }
                loop.call_soon_threadsafe(
                    self._schedule_broadcast,
                    {"type": "mining_progress", "payload": payload},
                )

        mined: Block | None = None
        try:
            mined = await asyncio.wait_for(
                asyncio.to_thread(
                    mine_block_with_progress,
                    template,
                    max_nonce=max_nonce,
                    progress_interval=self.config.mining_progress_interval,
                    on_progress=on_progress,
                    stop_event=job.stop_event,
                ),
                timeout=self.config.mining_max_runtime_seconds,
            )
        except asyncio.TimeoutError:
            job.stop_event.set()
            job.error = f"Mining exceeded maximum allowed runtime of {self.config.mining_max_runtime_seconds}s"
        except Exception as exc:
            logger.error("Error during mining thread execution: %s", exc)
            job.error = str(exc)

        job.finished_at = time.time()
        job.elapsed_seconds = job.finished_at - (job.started_at or job.finished_at)

        try:
            if job.stop_event.is_set():
                job.status = "CANCELLED"
                await self._safe_broadcast({
                    "type": "mining_cancelled",
                    "payload": {"job_id": job.id},
                })
            elif mined is not None:
                job.status = "FOUND"
                job.result_hash = mined.hash()
                job.nonce = mined.nonce
                await self._safe_broadcast({
                    "type": "block_found",
                    "payload": {
                        "job_id": job.id,
                        "height": job.template_height,
                        "hash": job.result_hash,
                        "nonce": job.nonce,
                    },
                })

                # Validate and commit through node
                accepted = await self.node.accept_block(mined)
                job.accepted = accepted

                if accepted:
                    job.status = "ACCEPTED"
                    await self._safe_broadcast({
                        "type": "block_accepted",
                        "payload": {
                            "job_id": job.id,
                            "height": job.template_height,
                            "hash": job.result_hash,
                            "miner_address": job.miner_address,
                            "reward": job.total_reward,
                        },
                    })
                else:
                    current_status = await self.node.get_status()
                    if current_status["tip_hash"] != job.previous_hash:
                        job.status = "STALE"
                        job.error = "Another block won the race. The template previous hash is no longer the current tip."
                    else:
                        job.status = "FAILED"
                        job.error = "Block was rejected by node consensus rules."

                    await self._safe_broadcast({
                        "type": "mining_finished",
                        "payload": {
                            "job_id": job.id,
                            "status": job.status,
                            "error": job.error,
                        },
                    })
            else:
                if not job.error:
                    job.error = f"No valid proof-of-work found within max_nonce ({max_nonce})."
                job.status = "FAILED"
                await self._safe_broadcast({
                    "type": "mining_finished",
                    "payload": {
                        "job_id": job.id,
                        "status": job.status,
                        "error": job.error,
                    },
                })
        finally:
            async with self._lock:
                if self._active_job_id == job.id:
                    self._active_job_id = None

    def get_job(self, job_id: str) -> MiningJob:
        job = self._jobs.get(job_id)
        if job is None:
            raise APIError(404, "JOB_NOT_FOUND", f"Mining job '{job_id}' not found")
        return job

    def get_active_job(self) -> MiningJob | None:
        if self._active_job_id:
            job = self._jobs.get(self._active_job_id)
            if job and job.status in ("QUEUED", "MINING"):
                return job
        return None

    async def cancel_job(self, job_id: str, user_id: int | None = None) -> dict[str, Any]:
        job = self.get_job(job_id)
        if job.status not in ("QUEUED", "MINING"):
            return {"job_id": job_id, "cancelled": False}

        job.stop_event.set()
        job.status = "CANCELLED"
        job.finished_at = time.time()
        job.elapsed_seconds = job.finished_at - (job.started_at or job.finished_at)

        async with self._lock:
            if self._active_job_id == job_id:
                self._active_job_id = None

        await self._safe_broadcast({
            "type": "mining_cancelled",
            "payload": {"job_id": job.id},
        })
        return {"job_id": job_id, "cancelled": True}

    async def close(self) -> None:
        self._closed = True
        if self._active_job_id:
            job = self._jobs.get(self._active_job_id)
            if job:
                job.stop_event.set()
        if self._worker_task and not self._worker_task.done():
            self._worker_task.cancel()
            try:
                await self._worker_task
            except asyncio.CancelledError:
                pass
