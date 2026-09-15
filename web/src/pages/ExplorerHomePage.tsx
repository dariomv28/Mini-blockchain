import React, { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { Activity, AlertCircle, ArrowRight, Compass, RefreshCw } from "lucide-react";
import { getExplorerStats, getLatestBlocks, getMempool } from "../api/explorer";
import { ExplorerBlockListItem, ExplorerMempoolResponse, ExplorerStats } from "../types/explorer";
import { SearchBar } from "../components/explorer/SearchBar";
import { ChainStats } from "../components/explorer/ChainStats";
import { LatestBlocksTable } from "../components/explorer/LatestBlocksTable";
import { HashLink } from "../components/explorer/HashLink";

export const ExplorerHomePage: React.FC = () => {
  const [stats, setStats] = useState<ExplorerStats | null>(null);
  const [blocks, setBlocks] = useState<ExplorerBlockListItem[]>([]);
  const [mempool, setMempool] = useState<ExplorerMempoolResponse | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const loadData = async () => {
    try {
      setIsLoading(true);
      const [s, b, m] = await Promise.all([
        getExplorerStats(),
        getLatestBlocks(10, 0),
        getMempool(),
      ]);
      setStats(s);
      setBlocks(b.blocks);
      setMempool(m);
      setError(null);
    } catch (err: any) {
      setError(err?.message || "Failed to load blockchain explorer data");
    } finally {
      setIsLoading(false);
    }
  };

  useEffect(() => {
    loadData();
    // Periodic refresh every 10 seconds
    const interval = setInterval(loadData, 10000);
    return () => clearInterval(interval);
  }, []);

  return (
    <div className="space-y-8 animate-in fade-in duration-500 pb-12">
      {/* Hero Search Section */}
      <div className="relative overflow-hidden rounded-3xl bg-gradient-to-br from-slate-900/90 via-slate-950 to-[#080c14] border border-slate-800 p-6 sm:p-10 shadow-2xl">
        <div className="absolute -top-32 -right-32 w-80 h-80 bg-emerald-500/10 rounded-full blur-3xl pointer-events-none" />
        <div className="absolute -bottom-32 -left-32 w-80 h-80 bg-cyan-500/10 rounded-full blur-3xl pointer-events-none" />

        <div className="relative z-10 max-w-3xl mx-auto text-center space-y-4">
          <div className="inline-flex items-center gap-2 px-3 py-1 rounded-full bg-emerald-500/10 border border-emerald-500/30 text-emerald-400 text-xs font-mono font-bold">
            <Compass className="w-3.5 h-3.5" />
            PyChain Public Ledger Explorer
          </div>

          <h1 className="text-3xl sm:text-4xl lg:text-5xl font-black tracking-tight text-white">
            Explore the PyChain Blockchain
          </h1>

          <p className="text-sm sm:text-base text-slate-400">
            Realtime transparency into blocks, transactions, miner fees, and address balances.
          </p>

          <div className="pt-2">
            <SearchBar />
          </div>
        </div>
      </div>

      {/* Background refresh error banner */}
      {error && stats && (
        <div className="rounded-xl border border-amber-500/30 bg-amber-500/10 p-3 text-xs text-amber-300 flex items-center justify-between animate-in fade-in duration-300">
          <div className="flex items-center gap-2">
            <AlertCircle className="w-4 h-4 text-amber-400 shrink-0" />
            <span>Could not refresh live chain data ({error}). Showing previous snapshot.</span>
          </div>
          <button
            onClick={loadData}
            className="px-2 py-1 bg-amber-500/20 hover:bg-amber-500/30 rounded text-amber-200 font-semibold"
          >
            Retry
          </button>
        </div>
      )}

      {/* Initial load failure state */}
      {error && !stats && (
        <div className="space-y-4 py-12 max-w-xl mx-auto text-center animate-in fade-in duration-300 bg-slate-900/60 border border-slate-800 rounded-2xl p-6">
          <div className="w-12 h-12 rounded-2xl bg-rose-500/10 border border-rose-500/30 flex items-center justify-center text-rose-400 mx-auto">
            <AlertCircle className="w-6 h-6" />
          </div>
          <div>
            <h2 className="text-lg font-bold text-white">Failed to Load Explorer Data</h2>
            <p className="text-xs text-rose-400/90 mt-1">{error}</p>
          </div>
          <button
            onClick={loadData}
            className="inline-flex items-center gap-2 px-4 py-2 rounded-xl bg-slate-800 text-slate-200 hover:bg-slate-700 text-xs font-semibold"
          >
            <RefreshCw className="w-4 h-4" />
            Retry
          </button>
        </div>
      )}

      {/* Network Metrics Stats Row */}
      <section>
        <ChainStats stats={stats} isLoading={isLoading && !stats} />
      </section>

      {/* Two Column Section: Latest Blocks & Mempool Quick View */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6 items-start">
        {/* Left Column: Latest Blocks (2 cols) */}
        <div className="lg:col-span-2">
          <LatestBlocksTable blocks={blocks} isLoading={isLoading} />
        </div>

        {/* Right Column: Mempool Activity Card (1 col) */}
        <div className="bg-slate-900/70 border border-slate-800/80 rounded-2xl p-5 sm:p-6 backdrop-blur-sm shadow-xl flex flex-col justify-between">
          <div>
            <div className="flex items-center justify-between pb-4 border-b border-slate-800 mb-4">
              <div className="flex items-center gap-2.5">
                <div className="w-8 h-8 rounded-lg bg-amber-500/10 border border-amber-500/30 flex items-center justify-center text-amber-400">
                  <Activity className="w-4 h-4" />
                </div>
                <div>
                  <h2 className="font-bold text-base text-white">Mempool Queue</h2>
                  <p className="text-xs text-slate-400">Pending unconfirmed transactions</p>
                </div>
              </div>

              <Link
                to="/explorer/mempool"
                className="text-xs text-amber-400 hover:text-amber-300 flex items-center gap-1 font-semibold"
              >
                View all
                <ArrowRight className="w-3.5 h-3.5" />
              </Link>
            </div>

            {mempool && mempool.transactions.length > 0 ? (
              <div className="space-y-3">
                {mempool.transactions.slice(0, 5).map((tx) => (
                  <div
                    key={tx.txid}
                    className="p-3 rounded-xl bg-slate-950/60 border border-slate-800/70 flex items-center justify-between text-xs"
                  >
                    <div>
                      <HashLink value={tx.txid} type="tx" truncateLength={6} />
                      <div className="text-[11px] text-slate-400 mt-0.5">
                        {tx.inputs_count} in • {tx.outputs_count} out • {tx.size_bytes}B
                      </div>
                    </div>
                    <div className="text-right font-mono">
                      <span className="text-emerald-400 font-bold">+{tx.fee} PYC</span>
                      <span className="block text-[10px] text-slate-500">fee</span>
                    </div>
                  </div>
                ))}
              </div>
            ) : (
              <div className="py-12 text-center text-slate-500 text-xs">
                Mempool is currently empty.
              </div>
            )}
          </div>

          <div className="mt-6 pt-4 border-t border-slate-800 text-xs text-slate-400 flex items-center justify-between">
            <span>Total Queue Bytes:</span>
            <strong className="text-slate-200 font-mono">
              {mempool?.total_bytes.toLocaleString() ?? 0} B
            </strong>
          </div>
        </div>
      </div>
    </div>
  );
};
