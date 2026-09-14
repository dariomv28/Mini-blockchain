import React, { useState } from "react";
import { MiningJob } from "../types/mining";
import {
  AlertTriangle,
  Ban,
  Check,
  Coins,
  Copy,
  RefreshCw,
  Trophy,
  X,
  XCircle,
} from "lucide-react";

interface BlockFoundCardProps {
  job: MiningJob;
  onDismiss: () => void;
  onRebuild: () => void;
}

export const BlockFoundCard: React.FC<BlockFoundCardProps> = ({
  job,
  onDismiss,
  onRebuild,
}) => {
  const [copiedHash, setCopiedHash] = useState(false);

  const handleCopyHash = () => {
    if (job.result_hash) {
      navigator.clipboard.writeText(job.result_hash);
      setCopiedHash(true);
      setTimeout(() => setCopiedHash(false), 2000);
    }
  };

  if (job.status === "ACCEPTED") {
    return (
      <div className="relative overflow-hidden bg-gradient-to-br from-emerald-950/70 via-slate-900 to-slate-950 border border-emerald-500/50 rounded-2xl p-6 backdrop-blur-md shadow-2xl shadow-emerald-500/20">
        <div className="absolute -top-12 -right-12 w-48 h-48 bg-emerald-500/10 rounded-full blur-2xl pointer-events-none" />

        <div className="flex items-start justify-between relative z-10 pb-4 border-b border-emerald-500/20">
          <div className="flex items-center gap-3.5">
            <div className="w-11 h-11 rounded-2xl bg-emerald-500/20 border border-emerald-500/40 flex items-center justify-center text-emerald-400 shadow-lg shadow-emerald-500/20">
              <Trophy className="w-6 h-6 animate-bounce" />
            </div>
            <div>
              <div className="flex items-center gap-2">
                <h3 className="font-black text-lg text-white">
                  Block #{job.template_height} Found &amp; Accepted!
                </h3>
                <span className="text-xs font-mono font-bold px-2 py-0.5 rounded-full bg-emerald-500/20 text-emerald-300 border border-emerald-500/40">
                  Consensus Confirmed
                </span>
              </div>
              <p className="text-xs text-slate-300 mt-0.5">
                Proof-of-work solution was verified and committed to the blockchain.
              </p>
            </div>
          </div>

          <button
            onClick={onDismiss}
            className="text-slate-400 hover:text-white p-1 rounded-lg hover:bg-slate-800 transition-colors"
            title="Dismiss notification"
          >
            <X className="w-5 h-5" />
          </button>
        </div>

        {/* Details */}
        <div className="grid grid-cols-1 sm:grid-cols-3 gap-3 mt-4 relative z-10">
          <div className="bg-slate-950/60 border border-emerald-500/20 rounded-xl p-3">
            <span className="text-[11px] uppercase tracking-wider text-slate-400 font-semibold block mb-1">
              Winning Nonce
            </span>
            <span className="font-mono text-lg font-bold text-amber-400">
              {job.nonce?.toLocaleString() ?? "N/A"}
            </span>
          </div>

          <div className="bg-slate-950/60 border border-emerald-500/20 rounded-xl p-3">
            <span className="text-[11px] uppercase tracking-wider text-slate-400 font-semibold block mb-1">
              Hashes Computed
            </span>
            <span className="font-mono text-lg font-bold text-cyan-400">
              {job.hashes_tried.toLocaleString()} ({job.elapsed_seconds.toFixed(1)}s)
            </span>
          </div>

          <div className="bg-slate-950/60 border border-emerald-500/20 rounded-xl p-3">
            <span className="text-[11px] uppercase tracking-wider text-slate-400 font-semibold block mb-1">
              Reward Credited
            </span>
            <span className="font-mono text-lg font-bold text-emerald-400 flex items-center gap-1">
              <Coins className="w-4 h-4" />
              +{job.total_reward} PYC
            </span>
          </div>
        </div>

        {/* Hash Display */}
        {job.result_hash && (
          <div className="mt-3 bg-slate-950/80 border border-emerald-500/20 rounded-xl p-3 relative z-10 flex items-center justify-between">
            <div className="min-w-0 mr-2">
              <span className="text-[10px] uppercase tracking-wider text-slate-400 font-semibold block">
                Mined Block Hash
              </span>
              <span className="font-mono text-xs text-slate-200 font-medium truncate block">
                {job.result_hash}
              </span>
            </div>
            <button
              onClick={handleCopyHash}
              className="p-1.5 hover:text-white text-slate-400 hover:bg-slate-800 rounded-lg transition-colors flex-shrink-0"
              title="Copy Hash"
            >
              {copiedHash ? (
                <Check className="w-4 h-4 text-emerald-400" />
              ) : (
                <Copy className="w-4 h-4" />
              )}
            </button>
          </div>
        )}
      </div>
    );
  }

  if (job.status === "STALE") {
    return (
      <div className="bg-gradient-to-br from-amber-950/50 via-slate-900 to-slate-950 border border-amber-500/40 rounded-2xl p-6 backdrop-blur-md shadow-xl">
        <div className="flex items-start justify-between pb-3 border-b border-amber-500/20">
          <div className="flex items-center gap-3">
            <div className="w-10 h-10 rounded-xl bg-amber-500/20 border border-amber-500/30 flex items-center justify-center text-amber-400">
              <AlertTriangle className="w-5 h-5" />
            </div>
            <div>
              <h3 className="font-bold text-base text-amber-300">
                Stale Block — Race Condition
              </h3>
              <p className="text-xs text-slate-300 mt-0.5">
                Another block won the race to extend the blockchain.
              </p>
            </div>
          </div>

          <button onClick={onDismiss} className="text-slate-400 hover:text-white">
            <X className="w-5 h-5" />
          </button>
        </div>

        <div className="mt-3 text-xs text-slate-300 space-y-2">
          <p>
            While your computer was searching for the winning nonce, another block at height #{job.template_height} was accepted into the chain first.
          </p>
          <p className="text-slate-400">
            This is a normal part of distributed consensus. Your candidate block is now stale because its parent hash does not match the latest tip.
          </p>
        </div>

        <div className="mt-4 pt-3 border-t border-slate-800 flex justify-end">
          <button
            onClick={onRebuild}
            className="flex items-center gap-1.5 text-xs font-bold px-4 py-2 rounded-xl bg-amber-500/20 hover:bg-amber-500/30 text-amber-300 border border-amber-500/30 transition-colors"
          >
            <RefreshCw className="w-3.5 h-3.5" />
            Build New Candidate from Latest Tip
          </button>
        </div>
      </div>
    );
  }

  if (job.status === "CANCELLED") {
    return (
      <div className="bg-slate-900/80 border border-slate-700/80 rounded-2xl p-5 backdrop-blur-md flex items-center justify-between">
        <div className="flex items-center gap-3">
          <div className="w-9 h-9 rounded-xl bg-slate-800 border border-slate-700 flex items-center justify-center text-slate-400">
            <Ban className="w-5 h-5" />
          </div>
          <div>
            <h4 className="font-bold text-sm text-slate-200">Mining Cancelled</h4>
            <p className="text-xs text-slate-400">
              The mining job was stopped. Nonce reached: {job.nonce ?? 0}
            </p>
          </div>
        </div>
        <button
          onClick={onDismiss}
          className="text-slate-400 hover:text-white p-1 rounded-lg hover:bg-slate-800"
        >
          <X className="w-4 h-4" />
        </button>
      </div>
    );
  }

  if (job.status === "FAILED") {
    return (
      <div className="bg-rose-950/40 border border-rose-500/30 rounded-2xl p-5 backdrop-blur-md flex items-center justify-between">
        <div className="flex items-center gap-3">
          <div className="w-9 h-9 rounded-xl bg-rose-500/20 border border-rose-500/30 flex items-center justify-center text-rose-400">
            <XCircle className="w-5 h-5" />
          </div>
          <div>
            <h4 className="font-bold text-sm text-rose-200">Mining Failed</h4>
            <p className="text-xs text-slate-400">
              {job.error || "Proof-of-work did not find a solution within bounds."}
            </p>
          </div>
        </div>
        <button
          onClick={onDismiss}
          className="text-slate-400 hover:text-white p-1 rounded-lg hover:bg-slate-800"
        >
          <X className="w-4 h-4" />
        </button>
      </div>
    );
  }

  return null;
};
