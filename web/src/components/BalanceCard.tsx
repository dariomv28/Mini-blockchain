import React from "react";
import { Link } from "react-router-dom";
import { AlertCircle, ArrowDownLeft, ArrowUpRight, Coins, HelpCircle, RefreshCw } from "lucide-react";
import { WalletSummary } from "../types/api";

interface BalanceCardProps {
  summary: WalletSummary | null;
  isLoading: boolean;
  isError?: boolean;
  error?: Error | null;
  onRefresh?: () => void;
}

export const BalanceCard: React.FC<BalanceCardProps> = ({
  summary,
  isLoading,
  isError,
  error,
  onRefresh,
}) => {
  const confirmed = summary?.confirmed_balance ?? 0;
  const available = summary?.available_balance ?? 0;
  const pendingOut = summary?.pending_outgoing ?? 0;
  const pendingIn = summary?.pending_incoming ?? 0;

  return (
    <div className="relative overflow-hidden rounded-2xl glass-panel p-6 border border-slate-800 shadow-xl">
      {/* Decorative gradient orb */}
      <div className="absolute top-0 right-0 -mr-16 -mt-16 w-64 h-64 bg-gradient-to-br from-emerald-500/15 via-cyan-500/10 to-transparent rounded-full blur-3xl pointer-events-none" />

      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4 pb-6 border-b border-slate-800/80">
        <div className="flex-1">
          <div className="flex items-center gap-2">
            <span className="text-xs font-semibold uppercase tracking-wider text-emerald-400 flex items-center gap-1.5">
              <Coins className="w-3.5 h-3.5" />
              Confirmed Balance
            </span>
            {onRefresh && (
              <button
                type="button"
                onClick={onRefresh}
                disabled={isLoading}
                title="Refresh balance"
                className="text-slate-500 hover:text-slate-300 transition-colors"
              >
                <RefreshCw className={`w-3.5 h-3.5 ${isLoading ? "animate-spin" : ""}`} />
              </button>
            )}
          </div>

          {isError ? (
            <div className="mt-3 flex items-center gap-3 p-3 rounded-xl bg-rose-500/10 border border-rose-500/20 text-rose-300">
              <AlertCircle className="w-5 h-5 shrink-0 text-rose-400" />
              <div className="flex-1">
                <p className="text-xs font-bold">Failed to load balance</p>
                <p className="text-[11px] text-rose-400/80">{error?.message || "Could not retrieve balance from node"}</p>
              </div>
              {onRefresh && (
                <button
                  type="button"
                  onClick={onRefresh}
                  className="px-2.5 py-1 rounded-lg bg-rose-500/20 hover:bg-rose-500/30 text-rose-200 text-xs font-semibold transition-colors"
                >
                  Retry
                </button>
              )}
            </div>
          ) : (
            <div className="mt-1 flex items-baseline gap-2">
              <span className="text-4xl sm:text-5xl font-extrabold tracking-tight text-white font-mono">
                {isLoading && !summary ? (
                  <span className="inline-block w-32 h-10 bg-slate-800 rounded animate-pulse" />
                ) : (
                  confirmed.toLocaleString()
                )}
              </span>
              <span className="text-lg font-bold text-emerald-400">PYC</span>
            </div>
          )}
        </div>

        {/* Quick action buttons */}
        <div className="flex items-center gap-2.5">
          <Link
            to="/app/send"
            id="quick-send-btn"
            className="flex items-center gap-2 px-4 py-2.5 rounded-xl bg-gradient-to-r from-emerald-500 to-teal-600 hover:from-emerald-400 hover:to-teal-500 text-slate-950 font-bold text-sm shadow-lg shadow-emerald-500/20 transition-all active:scale-95"
          >
            <ArrowUpRight className="w-4 h-4 stroke-[2.5]" />
            Send PYC
          </Link>
          <Link
            to="/app/receive"
            id="quick-receive-btn"
            className="flex items-center gap-2 px-4 py-2.5 rounded-xl bg-slate-800 hover:bg-slate-700 text-white font-semibold text-sm border border-slate-700/80 transition-all active:scale-95"
          >
            <ArrowDownLeft className="w-4 h-4 stroke-[2.5] text-cyan-400" />
            Receive
          </Link>
        </div>
      </div>

      {/* Secondary metrics grid */}
      <div className="grid grid-cols-1 sm:grid-cols-3 gap-4 pt-5">
        <div className="p-3.5 rounded-xl bg-slate-950/40 border border-slate-800/60">
          <div className="flex items-center justify-between text-xs text-slate-400">
            <span>Available to Spend</span>
            <span title="Confirmed UTXOs minus outputs already locked in mempool">
              <HelpCircle className="w-3.5 h-3.5 text-slate-500 hover:text-slate-300" />
            </span>
          </div>
          <p className="mt-1.5 font-mono text-lg font-bold text-slate-200">
            {isError ? (
              "—"
            ) : isLoading && !summary ? (
              <span className="inline-block w-16 h-5 bg-slate-800 rounded animate-pulse" />
            ) : (
              `${available.toLocaleString()} PYC`
            )}
          </p>
        </div>

        <div className="p-3.5 rounded-xl bg-slate-950/40 border border-slate-800/60">
          <div className="flex items-center justify-between text-xs text-amber-400/90">
            <span>Pending Outgoing</span>
            <span className="w-2 h-2 rounded-full bg-amber-400 animate-pulse" />
          </div>
          <p className="mt-1.5 font-mono text-lg font-bold text-amber-300">
            {isError ? (
              "—"
            ) : isLoading && !summary ? (
              <span className="inline-block w-16 h-5 bg-slate-800 rounded animate-pulse" />
            ) : (
              `-${pendingOut.toLocaleString()} PYC`
            )}
          </p>
        </div>

        <div className="p-3.5 rounded-xl bg-slate-950/40 border border-slate-800/60">
          <div className="flex items-center justify-between text-xs text-cyan-400/90">
            <span>Pending Incoming</span>
            <span className="w-2 h-2 rounded-full bg-cyan-400 animate-pulse" />
          </div>
          <p className="mt-1.5 font-mono text-lg font-bold text-cyan-300">
            {isError ? (
              "—"
            ) : isLoading && !summary ? (
              <span className="inline-block w-16 h-5 bg-slate-800 rounded animate-pulse" />
            ) : (
              `+${pendingIn.toLocaleString()} PYC`
            )}
          </p>
        </div>
      </div>
    </div>
  );
};
