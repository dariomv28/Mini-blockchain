import React from "react";
import { Link } from "react-router-dom";
import { Activity, Blocks, CheckCircle2, Hash, Users } from "lucide-react";
import { ExplorerStats } from "../../types/explorer";
import { HashLink } from "./HashLink";

interface ChainStatsProps {
  stats: ExplorerStats | null;
  isLoading?: boolean;
}

export const ChainStats: React.FC<ChainStatsProps> = ({ stats, isLoading = false }) => {
  if (isLoading || !stats) {
    return (
      <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-5 gap-3.5 animate-pulse">
        {[...Array(5)].map((_, i) => (
          <div
            key={i}
            className="h-24 rounded-2xl bg-slate-900/60 border border-slate-800/80 p-4"
          />
        ))}
      </div>
    );
  }

  return (
    <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-5 gap-3.5">
      {/* 1. Best Block Height */}
      <div className="bg-slate-900/80 border border-slate-800/90 rounded-2xl p-4 backdrop-blur-sm shadow-lg flex flex-col justify-between group hover:border-emerald-500/40 transition-colors">
        <div className="flex items-center justify-between text-slate-400 mb-1">
          <span className="text-xs font-semibold uppercase tracking-wider">Tip Height</span>
          <Blocks className="w-4 h-4 text-emerald-400 group-hover:scale-110 transition-transform" />
        </div>
        <div className="flex items-baseline gap-2">
          <span className="text-2xl sm:text-3xl font-black font-mono text-white">
            #{stats.height}
          </span>
          <span className="text-[11px] px-1.5 py-0.5 rounded bg-emerald-500/10 text-emerald-400 font-mono font-bold">
            Live
          </span>
        </div>
      </div>

      {/* 2. Tip Block Hash */}
      <div className="bg-slate-900/80 border border-slate-800/90 rounded-2xl p-4 backdrop-blur-sm shadow-lg flex flex-col justify-between group hover:border-cyan-500/40 transition-colors">
        <div className="flex items-center justify-between text-slate-400 mb-1">
          <span className="text-xs font-semibold uppercase tracking-wider">Tip Hash</span>
          <Hash className="w-4 h-4 text-cyan-400 group-hover:scale-110 transition-transform" />
        </div>
        <div className="pt-1">
          <HashLink
            value={stats.tip_hash}
            type="block"
            truncateLength={6}
            className="text-cyan-300 font-bold"
          />
        </div>
      </div>

      {/* 3. Pending Mempool Txs */}
      <Link
        to="/explorer/mempool"
        className="bg-slate-900/80 border border-slate-800/90 rounded-2xl p-4 backdrop-blur-sm shadow-lg flex flex-col justify-between group hover:border-amber-500/40 transition-all hover:bg-slate-900 cursor-pointer"
      >
        <div className="flex items-center justify-between text-slate-400 mb-1">
          <span className="text-xs font-semibold uppercase tracking-wider">Mempool</span>
          <Activity className="w-4 h-4 text-amber-400 group-hover:scale-110 transition-transform" />
        </div>
        <div className="flex items-baseline gap-2">
          <span className="text-2xl sm:text-3xl font-black font-mono text-amber-400">
            {stats.mempool_count}
          </span>
          <span className="text-xs text-slate-500">pending</span>
        </div>
      </Link>

      {/* 4. Active Peers */}
      <div className="bg-slate-900/80 border border-slate-800/90 rounded-2xl p-4 backdrop-blur-sm shadow-lg flex flex-col justify-between group hover:border-indigo-500/40 transition-colors">
        <div className="flex items-center justify-between text-slate-400 mb-1">
          <span className="text-xs font-semibold uppercase tracking-wider">Peers</span>
          <Users className="w-4 h-4 text-indigo-400 group-hover:scale-110 transition-transform" />
        </div>
        <div className="flex items-baseline gap-2">
          <span className="text-2xl sm:text-3xl font-black font-mono text-white">
            {stats.peer_count}
          </span>
          <span className="text-xs text-slate-500">connected</span>
        </div>
      </div>

      {/* 5. Total Confirmed Transactions */}
      <div className="col-span-2 md:col-span-1 bg-slate-900/80 border border-slate-800/90 rounded-2xl p-4 backdrop-blur-sm shadow-lg flex flex-col justify-between group hover:border-emerald-500/40 transition-colors">
        <div className="flex items-center justify-between text-slate-400 mb-1">
          <span className="text-xs font-semibold uppercase tracking-wider">Total Confirmed</span>
          <CheckCircle2 className="w-4 h-4 text-emerald-400 group-hover:scale-110 transition-transform" />
        </div>
        <div className="flex items-baseline gap-2">
          <span className="text-2xl sm:text-3xl font-black font-mono text-emerald-400">
            {stats.total_confirmed_transactions.toLocaleString()}
          </span>
          <span className="text-xs text-slate-500">txs</span>
        </div>
      </div>
    </div>
  );
};
