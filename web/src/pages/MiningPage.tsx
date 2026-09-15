import React, { useCallback, useEffect, useRef, useState } from "react";
import { useQueryClient } from "@tanstack/react-query";
import {
  CandidateTemplate,
  MempoolTransaction,
  MiningJob,
} from "../types/mining";
import {
  cancelMiningJob,
  getActiveMiningJob,
  getMempoolTransactions,
  getMiningJob,
  previewMiningTemplate,
  startMiningJob,
} from "../api/mining";
import { addWebSocketListener } from "../hooks/useWebSocket";
import { MempoolTable } from "../components/MempoolTable";
import { CandidateBlockCard } from "../components/CandidateBlockCard";
import { MiningJobCard } from "../components/MiningJobCard";
import { BlockFoundCard } from "../components/BlockFoundCard";
import { AlertCircle, Cpu } from "lucide-react";

export const MiningPage: React.FC = () => {
  const queryClient = useQueryClient();

  const [template, setTemplate] = useState<CandidateTemplate | null>(null);
  const [mempoolTxs, setMempoolTxs] = useState<MempoolTransaction[]>([]);
  const [activeJob, setActiveJob] = useState<MiningJob | null>(null);
  const [completedJob, setCompletedJob] = useState<MiningJob | null>(null);

  const [isLoadingTemplate, setIsLoadingTemplate] = useState<boolean>(false);
  const [isLoadingMempool, setIsLoadingMempool] = useState<boolean>(false);
  const [isStartingJob, setIsStartingJob] = useState<boolean>(false);
  const [isCancelling, setIsCancelling] = useState<boolean>(false);
  const [errorMsg, setErrorMsg] = useState<string | null>(null);

  const activeJobIdRef = useRef<string | null>(null);
  activeJobIdRef.current = activeJob?.id || null;
  const lastTipHashRef = useRef<string | null>(null);
  const lastPendingCountRef = useRef<number | null>(null);

  // Load mempool transactions
  const loadMempool = useCallback(async () => {
    try {
      setIsLoadingMempool(true);
      const txs = await getMempoolTransactions();
      setMempoolTxs(txs);
    } catch {
      // Non-blocking
    } finally {
      setIsLoadingMempool(false);
    }
  }, []);

  // Build candidate block template
  const buildTemplate = useCallback(async () => {
    try {
      setIsLoadingTemplate(true);
      setErrorMsg(null);
      const tpl = await previewMiningTemplate();
      setTemplate(tpl);
    } catch (err: any) {
      setErrorMsg(err?.message || "Failed to generate candidate block template");
    } finally {
      setIsLoadingTemplate(false);
    }
  }, []);

  // Check for existing active job on mount
  const checkActiveJob = useCallback(async () => {
    try {
      const job = await getActiveMiningJob();
      if (job && (job.status === "QUEUED" || job.status === "MINING")) {
        setActiveJob(job);
      }
    } catch {
      // Non-blocking
    }
  }, []);

  // Initial load
  useEffect(() => {
    loadMempool();
    buildTemplate();
    checkActiveJob();
  }, [loadMempool, buildTemplate, checkActiveJob]);

  // WebSocket Event Dispatcher
  useEffect(() => {
    const unsubscribe = addWebSocketListener((event) => {
      if (!event || !event.type) return;

      switch (event.type) {
        case "mining_started":
          if (event.payload?.job_id) {
            setActiveJob((prev) => ({
              ...(prev || ({} as MiningJob)),
              id: event.payload.job_id,
              status: "MINING",
              miner_address: event.payload.miner_address,
              template_height: event.payload.height,
              difficulty: event.payload.difficulty,
              transaction_count: event.payload.transaction_count,
              hashes_tried: 0,
              elapsed_seconds: 0,
              subsidy: 50,
              fees: 0,
              total_reward: 50,
              created_at: Date.now() / 1000,
            }));
          }
          break;

        case "mining_progress":
          if (event.payload?.job_id && activeJobIdRef.current === event.payload.job_id) {
            setActiveJob((prev) => {
              if (!prev) return null;
              return {
                ...prev,
                nonce: event.payload.nonce,
                hashes_tried: event.payload.hashes_tried,
                current_hash: event.payload.hash,
                elapsed_seconds: event.payload.elapsed_seconds ?? prev.elapsed_seconds,
              };
            });
          }
          break;

        case "block_found":
          if (event.payload?.job_id && activeJobIdRef.current === event.payload.job_id) {
            setActiveJob((prev) =>
              prev
                ? {
                    ...prev,
                    status: "FOUND",
                    result_hash: event.payload.hash,
                    nonce: event.payload.nonce,
                    hashes_tried: event.payload.hashes_tried ?? prev.hashes_tried,
                    elapsed_seconds: event.payload.elapsed_seconds ?? prev.elapsed_seconds,
                  }
                : null
            );
          }
          break;

        case "block_accepted":
          if (event.payload?.job_id && activeJobIdRef.current === event.payload.job_id) {
            setActiveJob((prev) => {
              const finished: MiningJob = {
                ...(prev || ({} as MiningJob)),
                id: event.payload.job_id,
                status: "ACCEPTED",
                result_hash: event.payload.hash,
                accepted: true,
                template_height: event.payload.height,
                total_reward: event.payload.reward ?? 50,
                nonce: event.payload.nonce ?? prev?.nonce,
                hashes_tried: event.payload.hashes_tried ?? prev?.hashes_tried ?? 0,
                elapsed_seconds: event.payload.elapsed_seconds ?? prev?.elapsed_seconds ?? 0,
              };
              setCompletedJob(finished);
              return null;
            });
            getMiningJob(event.payload.job_id)
              .then((finalJob) => {
                setCompletedJob(finalJob);
              })
              .catch(() => {});
            // Update wallet balance, mempool, and new template
            queryClient.invalidateQueries({ queryKey: ["wallet"] });
            loadMempool();
            buildTemplate();
          }
          break;

        case "mining_cancelled":
          if (event.payload?.job_id && activeJobIdRef.current === event.payload.job_id) {
            setActiveJob((prev) => {
              if (prev) {
                setCompletedJob({
                  ...prev,
                  status: "CANCELLED",
                  nonce: event.payload.nonce ?? prev.nonce,
                  hashes_tried: event.payload.hashes_tried ?? prev.hashes_tried,
                  elapsed_seconds: event.payload.elapsed_seconds ?? prev.elapsed_seconds,
                });
              }
              return null;
            });
            getMiningJob(event.payload.job_id)
              .then((finalJob) => {
                setCompletedJob(finalJob);
              })
              .catch(() => {});
          }
          break;

        case "mining_finished":
          if (event.payload?.job_id && activeJobIdRef.current === event.payload.job_id) {
            setActiveJob((prev) => {
              if (prev) {
                setCompletedJob({
                  ...prev,
                  status: event.payload.status,
                  error: event.payload.error,
                  nonce: event.payload.nonce ?? prev.nonce,
                  hashes_tried: event.payload.hashes_tried ?? prev.hashes_tried,
                  elapsed_seconds: event.payload.elapsed_seconds ?? prev.elapsed_seconds,
                });
              }
              return null;
            });
            getMiningJob(event.payload.job_id)
              .then((finalJob) => {
                setCompletedJob(finalJob);
              })
              .catch(() => {});
          }
          break;

        case "node_status":
          // Only refresh mempool when tip_hash or pending_count actually changes
          const tip = event.payload?.tip_hash;
          const pending = event.payload?.pending_count;
          if (tip !== lastTipHashRef.current || pending !== lastPendingCountRef.current) {
            lastTipHashRef.current = tip;
            lastPendingCountRef.current = pending;
            loadMempool();
            buildTemplate();
          }
          break;
      }
    });

    return () => {
      unsubscribe();
    };
  }, [buildTemplate, loadMempool, queryClient]);

  // REST polling fallback when active job is running
  useEffect(() => {
    if (!activeJob) return;

    let backoffMultiplier = 1;
    let timeoutId: number;

    const poll = async () => {
      try {
        const polled = await getMiningJob(activeJob.id);
        backoffMultiplier = 1;
        if (
          polled.status === "ACCEPTED" ||
          polled.status === "FAILED" ||
          polled.status === "STALE" ||
          polled.status === "CANCELLED"
        ) {
          setActiveJob(null);
          setCompletedJob(polled);
          if (polled.status === "ACCEPTED") {
            queryClient.invalidateQueries({ queryKey: ["wallet"] });
            loadMempool();
            buildTemplate();
          }
          return;
        } else {
          setActiveJob((prev) => ({
            ...(prev || polled),
            ...polled,
          }));
        }
      } catch (err: any) {
        if (err?.status === 429 || err?.message?.includes("429") || err?.response?.status === 429) {
          backoffMultiplier = Math.min(backoffMultiplier * 2, 8);
        }
      }
      timeoutId = window.setTimeout(poll, 1500 * backoffMultiplier);
    };

    timeoutId = window.setTimeout(poll, 1500);
    return () => clearTimeout(timeoutId);
  }, [activeJob?.id, buildTemplate, loadMempool, queryClient]);

  // Handler: Start Mining
  const handleStartMining = async () => {
    try {
      setIsStartingJob(true);
      setErrorMsg(null);
      setCompletedJob(null);

      const res = await startMiningJob({
        max_transactions: 100,
        max_bytes: 100000,
        max_nonce: 500000,
      });

      setActiveJob({
        id: res.job_id,
        status: "QUEUED",
        miner_address: template?.miner_address || "",
        created_at: Date.now() / 1000,
        template_height: template?.template_height || 1,
        previous_hash: template?.previous_block_hash || "",
        transaction_count: template?.transaction_count || 0,
        difficulty: template?.difficulty || 16,
        subsidy: template?.subsidy || 50,
        fees: template?.fees || 0,
        total_reward: template?.total_reward || 50,
        hashes_tried: 0,
        elapsed_seconds: 0,
      });
    } catch (err: any) {
      setErrorMsg(err?.message || "Failed to initiate mining job");
    } finally {
      setIsStartingJob(false);
    }
  };

  // Handler: Cancel Mining
  const handleCancelMining = async () => {
    if (!activeJob) return;
    try {
      setIsCancelling(true);
      const res = await cancelMiningJob(activeJob.id);
      if (res.cancelled) {
        setActiveJob(null);
        setCompletedJob({
          ...activeJob,
          status: "CANCELLED",
        });
      } else {
        // Not cancelled: check real status from server
        const current = await getMiningJob(activeJob.id);
        if (current.status !== "QUEUED" && current.status !== "MINING") {
          setActiveJob(null);
          setCompletedJob(current);
          if (current.status === "ACCEPTED") {
            queryClient.invalidateQueries({ queryKey: ["wallet"] });
            loadMempool();
            buildTemplate();
          }
        }
      }
    } catch (err: any) {
      setErrorMsg(err?.message || "Failed to cancel mining job");
    } finally {
      setIsCancelling(false);
    }
  };

  return (
    <div className="space-y-8 animate-in fade-in duration-500">
      {/* Page Header */}
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4">
        <div>
          <div className="flex items-center gap-2 mb-1">
            <div className="w-7 h-7 rounded-lg bg-emerald-500/10 border border-emerald-500/30 flex items-center justify-center text-emerald-400">
              <Cpu className="w-4 h-4" />
            </div>
            <span className="text-xs font-bold uppercase tracking-wider text-emerald-400 font-mono">
              Proof-of-Work Consensus
            </span>
          </div>
          <h1 className="text-2xl sm:text-3xl font-black tracking-tight text-white flex items-center gap-2.5">
            Mining Dashboard
            <span className="text-xs font-bold px-2 py-0.5 rounded-full bg-emerald-500/10 text-emerald-400 border border-emerald-500/30 font-mono">
              Phase 13
            </span>
          </h1>
          <p className="text-sm text-slate-400 mt-1 max-w-2xl">
            Inspect live mempool transactions, construct a candidate block template, and solve the Proof-of-Work hash puzzle to earn 50 PYC block rewards.
          </p>
        </div>
      </div>

      {/* Global Error Banner */}
      {errorMsg && (
        <div className="bg-rose-500/10 border border-rose-500/30 rounded-2xl p-4 flex items-center gap-3 text-rose-300 text-sm">
          <AlertCircle className="w-5 h-5 flex-shrink-0 text-rose-400" />
          <span className="flex-1 font-medium">{errorMsg}</span>
          <button
            onClick={() => setErrorMsg(null)}
            className="text-xs underline hover:text-white"
          >
            Dismiss
          </button>
        </div>
      )}

      {/* Active Mining Job Card (Shown while mining is active) */}
      {activeJob && (
        <MiningJobCard
          job={activeJob}
          onCancel={handleCancelMining}
          isCancelling={isCancelling}
        />
      )}

      {/* Completed Mining Outcome Card */}
      {completedJob && !activeJob && (
        <BlockFoundCard
          job={completedJob}
          onDismiss={() => setCompletedJob(null)}
          onRebuild={() => {
            setCompletedJob(null);
            buildTemplate();
          }}
        />
      )}

      {/* Two Column Layout: Candidate Block Card & Mempool Table */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6 items-stretch">
        <CandidateBlockCard
          template={template}
          isLoadingTemplate={isLoadingTemplate}
          isMiningActive={Boolean(activeJob)}
          isStartingJob={isStartingJob}
          onBuildTemplate={buildTemplate}
          onStartMining={handleStartMining}
        />

        <MempoolTable
          transactions={mempoolTxs}
          isLoading={isLoadingMempool}
          onRefresh={loadMempool}
        />
      </div>
    </div>
  );
};

export default MiningPage;
