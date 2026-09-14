import React from "react";
import { MiningJob } from "../types/mining";
import { Activity, Clock, Cpu, Hash, StopCircle, Zap } from "lucide-react";

interface MiningJobCardProps {
  job: MiningJob;
  onCancel: () => void;
  isCancelling?: boolean;
}

export const MiningJobCard: React.FC<MiningJobCardProps> = ({
  job,
  onCancel,
  isCancelling = false,
}) => {
  const hashrate =
    job.elapsed_seconds > 0
      ? Math.round(job.hashes_tried / job.elapsed_seconds)
      : job.hashes_tried;

  return (
    <div className="relative overflow-hidden bg-gradient-to-br from-slate-900/90 via-slate-950 to-[#080c14] border border-amber-500/40 rounded-2xl p-6 backdrop-blur-md shadow-2xl shadow-amber-500/10">
      {/* Background Animated Glow */}
      <div className="absolute -top-24 -right-24 w-64 h-64 bg-amber-500/10 rounded-full blur-3xl pointer-events-none animate-pulse" />
      <div className="absolute -bottom-24 -left-24 w-64 h-64 bg-emerald-500/10 rounded-full blur-3xl pointer-events-none animate-pulse" />

      {/* Header */}
      <div className="flex items-center justify-between pb-4 border-b border-slate-800/80 relative z-10">
        <div className="flex items-center gap-3">
          <div className="relative">
            <div className="w-10 h-10 rounded-xl bg-amber-500/20 border border-amber-500/40 flex items-center justify-center text-amber-400">
              <Cpu className="w-5 h-5 animate-spin" style={{ animationDuration: "3s" }} />
            </div>
            <span className="absolute -top-1 -right-1 flex h-3 w-3">
              <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-amber-400 opacity-75" />
              <span className="relative inline-flex rounded-full h-3 w-3 bg-amber-500" />
            </span>
          </div>
          <div>
            <h3 className="font-extrabold text-base text-white flex items-center gap-2">
              Proof-of-Work Mining in Progress
              <span className="text-[11px] font-mono px-2 py-0.5 rounded bg-amber-500/10 text-amber-400 border border-amber-500/30 uppercase font-semibold">
                Job: {job.id.slice(0, 8)}
              </span>
            </h3>
            <p className="text-xs text-slate-400">
              Computing SHA-256 hashes to satisfy difficulty target of {job.difficulty} leading zero bits
            </p>
          </div>
        </div>

        <button
          onClick={onCancel}
          disabled={isCancelling}
          className="flex items-center gap-1.5 text-xs font-bold px-3.5 py-2 rounded-xl bg-rose-500/10 hover:bg-rose-500/20 text-rose-400 border border-rose-500/30 transition-all disabled:opacity-50 hover:scale-[1.02] active:scale-95"
        >
          <StopCircle className="w-4 h-4" />
          {isCancelling ? "Cancelling..." : "Cancel Mining"}
        </button>
      </div>

      {/* Metrics Grid */}
      <div className="grid grid-cols-2 sm:grid-cols-4 gap-3 mt-5 relative z-10">
        <div className="bg-slate-950/70 border border-slate-800/80 rounded-xl p-3.5">
          <div className="flex items-center gap-1.5 text-slate-400 text-xs font-semibold uppercase tracking-wider mb-1">
            <Hash className="w-3.5 h-3.5 text-amber-400" />
            Current Nonce
          </div>
          <div className="font-mono text-xl sm:text-2xl font-black text-amber-400">
            {job.nonce?.toLocaleString() ?? "0"}
          </div>
        </div>

        <div className="bg-slate-950/70 border border-slate-800/80 rounded-xl p-3.5">
          <div className="flex items-center gap-1.5 text-slate-400 text-xs font-semibold uppercase tracking-wider mb-1">
            <Activity className="w-3.5 h-3.5 text-cyan-400" />
            Hashes Tried
          </div>
          <div className="font-mono text-xl sm:text-2xl font-black text-cyan-400">
            {job.hashes_tried.toLocaleString()}
          </div>
        </div>

        <div className="bg-slate-950/70 border border-slate-800/80 rounded-xl p-3.5">
          <div className="flex items-center gap-1.5 text-slate-400 text-xs font-semibold uppercase tracking-wider mb-1">
            <Zap className="w-3.5 h-3.5 text-emerald-400" />
            Hashrate
          </div>
          <div className="font-mono text-xl sm:text-2xl font-black text-emerald-400">
            {hashrate.toLocaleString()} <span className="text-xs font-normal text-slate-500">H/s</span>
          </div>
        </div>

        <div className="bg-slate-950/70 border border-slate-800/80 rounded-xl p-3.5">
          <div className="flex items-center gap-1.5 text-slate-400 text-xs font-semibold uppercase tracking-wider mb-1">
            <Clock className="w-3.5 h-3.5 text-indigo-400" />
            Elapsed Time
          </div>
          <div className="font-mono text-xl sm:text-2xl font-black text-indigo-400">
            {job.elapsed_seconds.toFixed(1)}s
          </div>
        </div>
      </div>

      {/* Latest Candidate Hash Live Stream */}
      <div className="mt-4 bg-slate-950/80 border border-slate-800/90 rounded-xl p-3.5 relative z-10">
        <div className="flex items-center justify-between text-xs text-slate-400 mb-1">
          <span className="font-semibold uppercase tracking-wider text-[11px]">Latest Candidate SHA-256 Hash</span>
          <span className="font-mono text-slate-500 text-[11px]">Target &lt; 2^(256 - {job.difficulty})</span>
        </div>
        <div className="font-mono text-xs sm:text-sm text-slate-300 font-semibold tracking-wider truncate bg-slate-900/60 p-2 rounded-lg border border-slate-800">
          {job.current_hash || "Searching for valid nonce..."}
        </div>
      </div>
    </div>
  );
};
