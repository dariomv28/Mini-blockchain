import React, { useEffect, useRef, useState } from "react";
import { Link, useParams } from "react-router-dom";
import {
  AlertCircle,
  ArrowLeft,
  CheckCircle2,
  ChevronRight,
  Clock,
  Coins,
  Loader2,
  Send,
} from "lucide-react";
import { getTransaction } from "../api/explorer";
import { EnrichedTransaction } from "../types/explorer";
import { HashLink } from "../components/explorer/HashLink";
import { addWebSocketListener } from "../hooks/useWebSocket";

export const TransactionDetailPage: React.FC = () => {
  const { txid } = useParams<{ txid: string }>();
  const [tx, setTx] = useState<EnrichedTransaction | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const currentTxidRef = useRef(txid);
  currentTxidRef.current = txid;

  useEffect(() => {
    let isCurrent = true;

    const fetchTx = async () => {
      if (!txid) return;
      try {
        setIsLoading(true);
        setError(null);
        const data = await getTransaction(txid);
        if (!isCurrent || currentTxidRef.current !== txid) return;
        setTx(data);
      } catch (err: any) {
        if (!isCurrent || currentTxidRef.current !== txid) return;
        setError(err?.message || "Failed to load transaction detail");
      } finally {
        if (isCurrent && currentTxidRef.current === txid) {
          setIsLoading(false);
        }
      }
    };

    fetchTx();

    return () => {
      isCurrent = false;
    };
  }, [txid]);

  // Realtime update: transition pending transaction to confirmed when block is accepted
  useEffect(() => {
    if (!txid || !tx || tx.status !== "pending") return;

    let isCurrent = true;

    const refreshTx = async () => {
      if (!isCurrent || currentTxidRef.current !== txid) return;
      try {
        const updated = await getTransaction(txid);
        if (isCurrent && currentTxidRef.current === txid) {
          setTx(updated);
        }
      } catch {
        // Non-blocking on background polling
      }
    };

    const removeListener = addWebSocketListener((evt) => {
      if (
        evt.type === "node_status" ||
        evt.type === "block_accepted" ||
        evt.type === "block_found" ||
        evt.type === "mining_finished"
      ) {
        refreshTx();
      }
    });

    const intervalId = window.setInterval(refreshTx, 1500);

    return () => {
      isCurrent = false;
      removeListener();
      clearInterval(intervalId);
    };
  }, [tx?.status, txid]);

  if (isLoading) {
    return (
      <div className="py-24 text-center">
        <Loader2 className="w-8 h-8 mx-auto animate-spin text-emerald-400 mb-3" />
        <p className="text-sm font-semibold text-slate-300 font-mono">
          Loading transaction data...
        </p>
      </div>
    );
  }

  if (error || !tx) {
    return (
      <div className="space-y-6 py-12 max-w-2xl mx-auto text-center">
        <div className="w-12 h-12 rounded-2xl bg-rose-500/10 border border-rose-500/30 flex items-center justify-center text-rose-400 mx-auto">
          <AlertCircle className="w-6 h-6" />
        </div>
        <div>
          <h2 className="text-xl font-bold text-white">Transaction Not Found</h2>
          <p className="text-sm text-slate-400 mt-1">
            {error || "Transaction does not exist in mempool or blockchain"}
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

  const totalOutput = tx.outputs.reduce((sum, out) => sum + out.amount, 0);

  return (
    <div className="space-y-6 animate-in fade-in duration-500 pb-12">
      {/* Breadcrumb Navigation */}
      <nav className="flex items-center gap-2 text-xs font-mono text-slate-400">
        <Link to="/explorer" className="hover:text-emerald-400 transition-colors">
          Explorer
        </Link>
        <ChevronRight className="w-3.5 h-3.5 text-slate-600" />
        <span className="text-slate-500">Transaction</span>
        <ChevronRight className="w-3.5 h-3.5 text-slate-600" />
        <span className="text-slate-200 font-bold truncate max-w-xs">{tx.txid}</span>
      </nav>

      {/* Overview Card */}
      <div className="bg-slate-900/80 border border-slate-800/90 rounded-2xl p-6 backdrop-blur-sm shadow-xl">
        <div className="flex flex-col sm:flex-row sm:items-center justify-between pb-5 border-b border-slate-800 gap-3">
          <div className="flex items-center gap-3">
            <div className="w-10 h-10 rounded-xl bg-emerald-500/10 border border-emerald-500/30 flex items-center justify-center text-emerald-400">
              {tx.is_coinbase ? <Coins className="w-5 h-5" /> : <Send className="w-5 h-5" />}
            </div>
            <div>
              <h1 className="text-lg sm:text-xl font-bold text-white flex items-center gap-2">
                Transaction Overview
                <span
                  className={`text-xs font-mono font-bold px-2.5 py-0.5 rounded-full ${
                    tx.status === "confirmed"
                      ? "bg-emerald-500/10 text-emerald-400 border border-emerald-500/30"
                      : "bg-amber-500/10 text-amber-400 border border-amber-500/30 animate-pulse"
                  }`}
                >
                  {tx.status === "confirmed" ? "Confirmed" : "Pending in Mempool"}
                </span>
              </h1>
              <p className="text-xs text-slate-400">
                {tx.is_coinbase ? "Coinbase block reward transaction" : "Peer-to-peer value transfer"}
              </p>
            </div>
          </div>

          <div className="text-right font-mono text-xs text-slate-400">
            <span>Transacted Value: </span>
            <strong className="text-emerald-400 font-bold text-base">
              {totalOutput} PYC
            </strong>
          </div>
        </div>

        {/* Details Grid */}
        <div className="grid grid-cols-1 md:grid-cols-2 gap-y-4 gap-x-8 mt-5 text-xs font-mono">
          <div>
            <span className="text-slate-400 block mb-1">Transaction ID (TxID)</span>
            <HashLink value={tx.txid} type="tx" truncate={false} className="break-all font-semibold" />
          </div>

          <div>
            <span className="text-slate-400 block mb-1">Status / Block</span>
            {tx.status === "confirmed" && tx.block_height !== null && tx.block_height !== undefined ? (
              <span className="text-slate-200 flex items-center gap-2">
                <CheckCircle2 className="w-4 h-4 text-emerald-400" />
                <span>Confirmed in </span>
                <Link
                  to={`/explorer/block/${tx.block_height}`}
                  className="text-emerald-400 font-bold hover:underline"
                >
                  Block #{tx.block_height}
                </Link>
              </span>
            ) : (
              <span className="text-amber-400 flex items-center gap-1.5">
                <Clock className="w-4 h-4 animate-spin" />
                Waiting to be mined into next block
              </span>
            )}
          </div>

          <div>
            <span className="text-slate-400 block mb-1">Timestamp</span>
            <span className="text-slate-200">
              {new Date(tx.timestamp * 1000).toUTCString()} ({tx.timestamp})
            </span>
          </div>

          <div className="flex items-center gap-6">
            <div>
              <span className="text-slate-400 block mb-1">Transaction Fee</span>
              <span className="text-cyan-400 font-bold">{tx.fee} PYC</span>
            </div>
            <div>
              <span className="text-slate-400 block mb-1">Size</span>
              <span className="text-slate-300">{tx.size_bytes.toLocaleString()} bytes</span>
            </div>
          </div>
        </div>
      </div>

      {/* Side-by-Side Inputs & Outputs Detailed Cards */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        {/* Left: Inputs Breakdown */}
        <div className="bg-slate-900/80 border border-slate-800/90 rounded-2xl p-5 backdrop-blur-sm shadow-xl space-y-3">
          <div className="flex items-center justify-between pb-3 border-b border-slate-800">
            <h2 className="text-sm font-bold text-white uppercase tracking-wider">
              Inputs ({tx.inputs.length})
            </h2>
            <span className="text-xs text-slate-400 font-mono">
              Total In:{" "}
              <strong className="text-slate-200">
                {tx.is_coinbase ? "New Coins" : `${totalOutput + tx.fee} PYC`}
              </strong>
            </span>
          </div>

          {tx.is_coinbase ? (
            <div className="py-8 text-center text-amber-400/90 text-xs italic bg-slate-950/40 rounded-xl p-4 border border-amber-500/20">
              <Coins className="w-6 h-6 mx-auto mb-2 text-amber-400 opacity-80" />
              Newly Created Coins (Coinbase Block Reward + Fees)
            </div>
          ) : (
            <div className="space-y-2">
              {tx.inputs.map((inp, idx) => (
                <div
                  key={idx}
                  className="p-3 rounded-xl bg-slate-950/60 border border-slate-800/60 flex flex-col gap-1.5 text-xs font-mono"
                >
                  <div className="flex items-center justify-between">
                    <span className="text-slate-400 text-[11px]">Source Address:</span>
                    {inp.source_address ? (
                      <HashLink value={inp.source_address} type="address" truncateLength={8} />
                    ) : (
                      <span className="text-slate-500">N/A</span>
                    )}
                  </div>
                  <div className="flex items-center justify-between">
                    <span className="text-slate-400 text-[11px]">Previous Outpoint:</span>
                    <HashLink value={inp.previous_tx_id} type="tx" truncateLength={6} />
                  </div>
                  {inp.amount !== null && inp.amount !== undefined && (
                    <div className="flex items-center justify-between pt-1 border-t border-slate-800/40">
                      <span className="text-slate-400 text-[11px]">Amount:</span>
                      <strong className="text-slate-200 font-bold">{inp.amount} PYC</strong>
                    </div>
                  )}
                </div>
              ))}
            </div>
          )}
        </div>

        {/* Right: Outputs Breakdown */}
        <div className="bg-slate-900/80 border border-slate-800/90 rounded-2xl p-5 backdrop-blur-sm shadow-xl space-y-3">
          <div className="flex items-center justify-between pb-3 border-b border-slate-800">
            <h2 className="text-sm font-bold text-white uppercase tracking-wider">
              Outputs ({tx.outputs.length})
            </h2>
            <span className="text-xs text-slate-400 font-mono">
              Total Out: <strong className="text-emerald-400">{totalOutput} PYC</strong>
            </span>
          </div>

          <div className="space-y-2">
            {tx.outputs.map((out, idx) => (
              <div
                key={idx}
                className="p-3 rounded-xl bg-slate-950/60 border border-slate-800/60 flex items-center justify-between text-xs font-mono"
              >
                <div>
                  <span className="text-[11px] text-slate-400 block mb-1">
                    Output #{out.index} to:
                  </span>
                  <HashLink value={out.recipient_address} type="address" truncateLength={8} />
                </div>
                <div className="text-right">
                  <span className="text-emerald-400 font-bold text-sm block">
                    +{out.amount} PYC
                  </span>
                </div>
              </div>
            ))}
          </div>
        </div>
      </div>
    </div>
  );
};
