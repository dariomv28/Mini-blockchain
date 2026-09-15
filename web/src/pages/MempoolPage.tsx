import React, { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { Activity, AlertCircle, ChevronRight, Loader2, RefreshCw } from "lucide-react";
import { getMempool } from "../api/explorer";
import { ExplorerMempoolResponse } from "../types/explorer";
import { HashLink } from "../components/explorer/HashLink";

export const MempoolPage: React.FC = () => {
  const [data, setData] = useState<ExplorerMempoolResponse | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [isRefreshing, setIsRefreshing] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const fetchMempool = async (showSpin = false) => {
    try {
      if (showSpin) setIsRefreshing(true);
      const res = await getMempool();
      setData(res);
      setError(null);
    } catch (err: any) {
      setError(err?.message || "Failed to load mempool data");
    } finally {
      setIsLoading(false);
      setIsRefreshing(false);
    }
  };

  useEffect(() => {
    fetchMempool();
    const interval = setInterval(() => fetchMempool(false), 5000);
    return () => clearInterval(interval);
  }, []);

  if (isLoading && !data && !error) {
    return (
      <div className="py-24 text-center">
        <Loader2 className="w-8 h-8 mx-auto animate-spin text-emerald-400 mb-3" />
        <p className="text-sm font-semibold text-slate-300 font-mono">
          Loading mempool status...
        </p>
      </div>
    );
  }

  if (error && !data) {
    return (
      <div className="space-y-6 py-12 max-w-2xl mx-auto text-center animate-in fade-in duration-300">
        <div className="w-12 h-12 rounded-2xl bg-rose-500/10 border border-rose-500/30 flex items-center justify-center text-rose-400 mx-auto">
          <AlertCircle className="w-6 h-6" />
        </div>
        <div>
          <h2 className="text-xl font-bold text-white">Failed to Load Mempool</h2>
          <p className="text-sm text-rose-400/90 mt-1">{error}</p>
        </div>
        <button
          onClick={() => {
            setIsLoading(true);
            fetchMempool(true);
          }}
          className="inline-flex items-center gap-2 px-4 py-2 rounded-xl bg-slate-800 text-slate-200 hover:bg-slate-700 text-xs font-semibold"
        >
          <RefreshCw className="w-4 h-4" />
          Retry
        </button>
      </div>
    );
  }

  return (
    <div className="space-y-6 animate-in fade-in duration-500 pb-12">
      {/* Breadcrumb Navigation */}
      <nav className="flex items-center gap-2 text-xs font-mono text-slate-400">
        <Link to="/explorer" className="hover:text-emerald-400 transition-colors">
          Explorer
        </Link>
        <ChevronRight className="w-3.5 h-3.5 text-slate-600" />
        <span className="text-slate-200 font-bold">Memory Pool (Mempool)</span>
      </nav>

      {error && data && (
        <div className="rounded-xl border border-amber-500/30 bg-amber-500/10 p-3 text-xs text-amber-300 flex items-center justify-between animate-in fade-in duration-300">
          <div className="flex items-center gap-2">
            <AlertCircle className="w-4 h-4 text-amber-400 shrink-0" />
            <span>Could not refresh live mempool ({error}). Showing previous snapshot.</span>
          </div>
          <button
            onClick={() => fetchMempool(true)}
            className="px-2 py-1 bg-amber-500/20 hover:bg-amber-500/30 rounded text-amber-200 font-semibold"
          >
            Retry
          </button>
        </div>
      )}

      {/* Header & Metrics */}
      <div className="bg-slate-900/80 border border-slate-800/90 rounded-2xl p-6 backdrop-blur-sm shadow-xl">
        <div className="flex flex-col sm:flex-row sm:items-center justify-between pb-5 border-b border-slate-800 gap-4">
          <div className="flex items-center gap-3">
            <div className="w-10 h-10 rounded-xl bg-amber-500/10 border border-amber-500/30 flex items-center justify-center text-amber-400">
              <Activity className="w-5 h-5" />
            </div>
            <div>
              <h1 className="text-xl font-bold text-white flex items-center gap-2">
                Live Memory Pool
                <span className="text-xs font-mono font-bold px-2 py-0.5 rounded-full bg-amber-500/10 text-amber-400 border border-amber-500/30 animate-pulse">
                  Live
                </span>
              </h1>
              <p className="text-xs text-slate-400">
                Unconfirmed transactions awaiting inclusion into future blocks
              </p>
            </div>
          </div>

          <button
            type="button"
            onClick={() => fetchMempool(true)}
            disabled={isRefreshing}
            className="flex items-center gap-1.5 px-3 py-1.5 rounded-xl border border-slate-800 bg-slate-900 hover:bg-slate-800 text-slate-300 text-xs font-mono font-medium transition-colors"
          >
            <RefreshCw className={`w-3.5 h-3.5 ${isRefreshing ? "animate-spin text-amber-400" : ""}`} />
            Refresh
          </button>
        </div>

        {/* Stats Row */}
        <div className="grid grid-cols-2 gap-4 mt-5 font-mono text-xs">
          <div className="bg-slate-950/60 p-4 rounded-xl border border-slate-800">
            <span className="text-slate-400 block mb-1">Pending Transactions</span>
            <span className="text-2xl font-black text-amber-400">
              {data?.count ?? 0}
            </span>
          </div>

          <div className="bg-slate-950/60 p-4 rounded-xl border border-slate-800">
            <span className="text-slate-400 block mb-1">Queue Byte Weight</span>
            <span className="text-2xl font-black text-slate-200">
              {(data?.total_bytes ?? 0).toLocaleString()} <span className="text-xs font-normal text-slate-500">bytes</span>
            </span>
          </div>
        </div>
      </div>

      {/* Transactions Table */}
      <div className="bg-slate-900/70 border border-slate-800/80 rounded-2xl p-5 sm:p-6 backdrop-blur-sm shadow-xl">
        <h2 className="text-sm font-bold text-white uppercase tracking-wider mb-4">
          Pending Transactions List ({data?.transactions.length ?? 0})
        </h2>

        <div className="overflow-x-auto">
          <table className="w-full text-left border-collapse text-xs font-mono">
            <thead>
              <tr className="border-b border-slate-800 text-[11px] font-semibold text-slate-400 uppercase tracking-wider">
                <th className="py-2.5 px-3">TxID</th>
                <th className="py-2.5 px-3">Inputs</th>
                <th className="py-2.5 px-3">Outputs</th>
                <th className="py-2.5 px-3">Size</th>
                <th className="py-2.5 px-3 text-right">Fee</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-800/50">
              {data?.transactions.map((tx) => (
                <tr key={tx.txid} className="hover:bg-slate-800/40 transition-colors">
                  <td className="py-3 px-3">
                    <HashLink value={tx.txid} type="tx" truncateLength={10} />
                  </td>

                  <td className="py-3 px-3 text-slate-300">
                    {tx.inputs_count}
                  </td>

                  <td className="py-3 px-3 text-slate-300">
                    {tx.outputs_count}
                  </td>

                  <td className="py-3 px-3 text-slate-400">
                    {tx.size_bytes} bytes
                  </td>

                  <td className="py-3 px-3 text-right font-bold text-emerald-400">
                    +{tx.fee} PYC
                  </td>
                </tr>
              ))}
            </tbody>
          </table>

          {data && data.transactions.length === 0 && (
            <div className="py-12 text-center text-slate-500 text-xs">
              Mempool is currently empty.
            </div>
          )}
        </div>
      </div>
    </div>
  );
};
