import React, { useEffect, useRef, useState } from "react";
import { Link, useParams } from "react-router-dom";
import {
  AlertCircle,
  ArrowDownLeft,
  ArrowLeft,
  ArrowUpRight,
  ChevronLeft,
  ChevronRight,
  Coins,
  History,
  Loader2,
  Wallet,
} from "lucide-react";
import { getAddressDetail } from "../api/explorer";
import { ExplorerAddressDetail } from "../types/explorer";
import { HashLink } from "../components/explorer/HashLink";
import { UtxoTable } from "../components/explorer/UtxoTable";

export const AddressDetailPage: React.FC = () => {
  const { address } = useParams<{ address: string }>();
  const [data, setData] = useState<ExplorerAddressDetail | null>(null);
  const [activeTab, setActiveTab] = useState<"history" | "utxos">("history");
  const [page, setPage] = useState(0);
  const [lastAddress, setLastAddress] = useState(address);
  const pageSize = 15;
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const currentAddressRef = useRef(address);
  currentAddressRef.current = address;

  // Immediately reset pagination & clear stale data if address changed
  if (address !== lastAddress) {
    setLastAddress(address);
    setPage(0);
    setData(null);
  }

  useEffect(() => {
    let isCurrent = true;

    const fetchAddress = async () => {
      if (!address) return;
      try {
        setIsLoading(true);
        setError(null);
        const res = await getAddressDetail(address, pageSize, page * pageSize);
        if (!isCurrent || currentAddressRef.current !== address) return;
        setData(res);
      } catch (err: any) {
        if (!isCurrent || currentAddressRef.current !== address) return;
        setError(err?.message || "Failed to load address detail");
      } finally {
        if (isCurrent && currentAddressRef.current === address) {
          setIsLoading(false);
        }
      }
    };

    fetchAddress();

    return () => {
      isCurrent = false;
    };
  }, [address, page]);

  if (isLoading && !data) {
    return (
      <div className="py-24 text-center">
        <Loader2 className="w-8 h-8 mx-auto animate-spin text-emerald-400 mb-3" />
        <p className="text-sm font-semibold text-slate-300 font-mono">
          Loading address data...
        </p>
      </div>
    );
  }

  if (error || !data) {
    return (
      <div className="space-y-6 py-12 max-w-2xl mx-auto text-center">
        <div className="w-12 h-12 rounded-2xl bg-rose-500/10 border border-rose-500/30 flex items-center justify-center text-rose-400 mx-auto">
          <AlertCircle className="w-6 h-6" />
        </div>
        <div>
          <h2 className="text-xl font-bold text-white">Address Not Found</h2>
          <p className="text-sm text-slate-400 mt-1">
            {error || "Could not retrieve address details"}
          </p>
        </div>
        <Link
          to="/explorer"
          className="inline-flex items-center gap-2 px-4 py-2 rounded-xl bg-slate-800 text-slate-200 hover:bg-slate-700 text-xs font-semibold"
        >
          <ArrowLeft className="w-4 h-4" />
          Back to Explorer
        </Link>
      </div>
    );
  }

  const totalPages = Math.ceil(data.total_transactions / pageSize);

  return (
    <div className="space-y-6 animate-in fade-in duration-500 pb-12">
      {/* Breadcrumb Navigation */}
      <nav className="flex items-center gap-2 text-xs font-mono text-slate-400">
        <Link to="/explorer" className="hover:text-emerald-400 transition-colors">
          Explorer
        </Link>
        <ChevronRight className="w-3.5 h-3.5 text-slate-600" />
        <span className="text-slate-500">Address</span>
        <ChevronRight className="w-3.5 h-3.5 text-slate-600" />
        <span className="text-slate-200 font-bold truncate max-w-xs">{data.address}</span>
      </nav>

      {/* Address Header Summary Card */}
      <div className="bg-slate-900/80 border border-slate-800/90 rounded-2xl p-6 backdrop-blur-sm shadow-xl">
        <div className="flex flex-col sm:flex-row sm:items-center justify-between pb-5 border-b border-slate-800 gap-4">
          <div className="flex items-center gap-3">
            <div className="w-10 h-10 rounded-xl bg-emerald-500/10 border border-emerald-500/30 flex items-center justify-center text-emerald-400">
              <Wallet className="w-5 h-5" />
            </div>
            <div>
              <span className="text-xs text-slate-400 font-mono">PYC Account Address</span>
              <div className="mt-0.5">
                <HashLink
                  value={data.address}
                  type="address"
                  truncate={false}
                  className="font-bold text-sm sm:text-base break-all"
                />
              </div>
            </div>
          </div>

          <div className="sm:text-right bg-slate-950/60 p-3.5 rounded-xl border border-slate-800">
            <span className="text-xs text-slate-400 font-mono block">Confirmed Balance</span>
            <span className="text-2xl font-black font-mono text-emerald-400">
              {data.confirmed_balance.toLocaleString()} PYC
            </span>
          </div>
        </div>

        {/* Stats Row */}
        <div className="grid grid-cols-2 sm:grid-cols-3 gap-4 mt-5 text-xs font-mono">
          <div>
            <span className="text-slate-400 block mb-1">Unspent Outputs (UTXOs)</span>
            <span className="text-white font-bold text-sm">{data.utxo_count}</span>
          </div>
          <div>
            <span className="text-slate-400 block mb-1">Total Transactions</span>
            <span className="text-white font-bold text-sm">{data.total_transactions}</span>
          </div>
        </div>
      </div>

      {/* Tabs & Content Section */}
      <div className="bg-slate-900/70 border border-slate-800/80 rounded-2xl p-5 sm:p-6 backdrop-blur-sm shadow-xl space-y-4">
        {/* Tab Headers */}
        <div className="flex items-center gap-2 border-b border-slate-800 pb-3">
          <button
            type="button"
            onClick={() => setActiveTab("history")}
            className={`flex items-center gap-2 px-4 py-2 rounded-xl text-xs font-bold transition-all ${
              activeTab === "history"
                ? "bg-slate-800 text-white border border-slate-700 shadow-sm"
                : "text-slate-400 hover:text-slate-200"
            }`}
          >
            <History className="w-3.5 h-3.5 text-emerald-400" />
            Transaction History ({data.total_transactions})
          </button>

          <button
            type="button"
            onClick={() => setActiveTab("utxos")}
            className={`flex items-center gap-2 px-4 py-2 rounded-xl text-xs font-bold transition-all ${
              activeTab === "utxos"
                ? "bg-slate-800 text-white border border-slate-700 shadow-sm"
                : "text-slate-400 hover:text-slate-200"
            }`}
          >
            <Coins className="w-3.5 h-3.5 text-amber-400" />
            Unspent Outputs ({data.utxo_count})
          </button>
        </div>

        {/* Tab 1: Transaction History */}
        {activeTab === "history" && (
          <div>
            <div className="overflow-x-auto">
              <table className="w-full text-left border-collapse text-xs font-mono">
                <thead>
                  <tr className="border-b border-slate-800 text-[11px] font-semibold text-slate-400 uppercase tracking-wider">
                    <th className="py-2.5 px-3">TxID</th>
                    <th className="py-2.5 px-3">Block / Status</th>
                    <th className="py-2.5 px-3">Direction</th>
                    <th className="py-2.5 px-3">Time</th>
                    <th className="py-2.5 px-3 text-right">Amount</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-slate-800/50">
                  {data.transactions.map((t) => (
                    <tr key={t.txid} className="hover:bg-slate-800/40 transition-colors">
                      <td className="py-3 px-3">
                        <HashLink value={t.txid} type="tx" truncateLength={8} />
                      </td>

                      <td className="py-3 px-3">
                        {t.status === "confirmed" && t.block_height !== null ? (
                          <Link
                            to={`/explorer/block/${t.block_height}`}
                            className="text-slate-300 hover:text-emerald-400 hover:underline"
                          >
                            #{t.block_height}
                          </Link>
                        ) : (
                          <span className="text-amber-400 font-semibold animate-pulse">
                            Pending
                          </span>
                        )}
                      </td>

                      <td className="py-3 px-3">
                        {t.direction === "mined" ? (
                          <span className="inline-flex items-center gap-1 text-[10px] font-bold px-2 py-0.5 rounded-full bg-amber-500/10 text-amber-400 border border-amber-500/30">
                            <Coins className="w-3 h-3" />
                            Mined
                          </span>
                        ) : t.direction === "sent" ? (
                          <span className="inline-flex items-center gap-1 text-[10px] font-bold px-2 py-0.5 rounded-full bg-rose-500/10 text-rose-400 border border-rose-500/30">
                            <ArrowUpRight className="w-3 h-3" />
                            Sent
                          </span>
                        ) : (
                          <span className="inline-flex items-center gap-1 text-[10px] font-bold px-2 py-0.5 rounded-full bg-emerald-500/10 text-emerald-400 border border-emerald-500/30">
                            <ArrowDownLeft className="w-3 h-3" />
                            Received
                          </span>
                        )}
                      </td>

                      <td className="py-3 px-3 text-slate-400">
                        {new Date(t.timestamp * 1000).toLocaleTimeString()}
                      </td>

                      <td className="py-3 px-3 text-right font-bold">
                        <span
                          className={
                            t.direction === "sent" ? "text-rose-400" : "text-emerald-400"
                          }
                        >
                          {t.direction === "sent" ? "-" : "+"}
                          {t.amount} PYC
                        </span>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>

              {data.transactions.length === 0 && (
                <div className="py-8 text-center text-slate-500 text-xs">
                  No transaction history recorded for this address.
                </div>
              )}
            </div>

            {/* Pagination Controls */}
            {totalPages > 1 && (
              <div className="flex items-center justify-between pt-4 border-t border-slate-800 text-xs font-mono text-slate-400">
                <span>
                  Page {page + 1} of {totalPages}
                </span>
                <div className="flex items-center gap-2">
                  <button
                    type="button"
                    disabled={page <= 0}
                    onClick={() => setPage((p) => Math.max(0, p - 1))}
                    className="p-1.5 rounded-lg border border-slate-800 bg-slate-900 hover:bg-slate-800 disabled:opacity-30 disabled:hover:bg-slate-900"
                  >
                    <ChevronLeft className="w-4 h-4" />
                  </button>
                  <button
                    type="button"
                    disabled={page >= totalPages - 1}
                    onClick={() => setPage((p) => p + 1)}
                    className="p-1.5 rounded-lg border border-slate-800 bg-slate-900 hover:bg-slate-800 disabled:opacity-30 disabled:hover:bg-slate-900"
                  >
                    <ChevronRight className="w-4 h-4" />
                  </button>
                </div>
              </div>
            )}
          </div>
        )}

        {/* Tab 2: UTXOs */}
        {activeTab === "utxos" && <UtxoTable utxos={data.utxos} />}
      </div>
    </div>
  );
};
