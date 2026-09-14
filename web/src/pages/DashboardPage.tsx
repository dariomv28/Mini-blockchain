import React from "react";
import { useQuery } from "@tanstack/react-query";
import { useAuth } from "../auth/AuthContext";
import * as walletApi from "../api/wallet";
import { BalanceCard } from "../components/BalanceCard";
import { AddressCard } from "../components/AddressCard";
import { TransactionRow } from "../components/TransactionRow";
import { AlertCircle, ArrowUpRight, History, Inbox, RefreshCw } from "lucide-react";
import { Link } from "react-router-dom";

export const DashboardPage: React.FC = () => {
  const { user, wallet } = useAuth();

  const {
    data: summary,
    isLoading: isSummaryLoading,
    isError: isSummaryError,
    error: summaryError,
    refetch: refetchSummary,
  } = useQuery(["wallet", user?.id], walletApi.getWalletSummary, {
    enabled: !!user?.id,
    staleTime: 5000,
  });

  const {
    data: transactions,
    isLoading: isTxLoading,
    isError: isTxError,
    error: txError,
    refetch: refetchTx,
  } = useQuery(["wallet", "transactions", user?.id], () => walletApi.getTransactionHistory(0, 10), {
    enabled: !!user?.id,
    staleTime: 5000,
  });

  const handleManualRefresh = () => {
    refetchSummary();
    refetchTx();
  };

  return (
    <div className="space-y-8 animate-fadeIn">
      {/* Top greeting bar */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4">
        <div>
          <h1 className="text-2xl sm:text-3xl font-extrabold text-white tracking-tight">
            Welcome back, <span className="text-emerald-400">{user?.username}</span>
          </h1>
          <p className="mt-1 text-sm text-slate-400">
            Overview of your blockchain holdings and transaction activity
          </p>
        </div>

        <button
          type="button"
          onClick={handleManualRefresh}
          className="inline-flex items-center gap-2 self-start sm:self-auto px-3.5 py-2 rounded-xl bg-slate-900 hover:bg-slate-800 text-slate-300 hover:text-white border border-slate-800 text-xs font-semibold transition-colors"
        >
          <RefreshCw
            className={`w-3.5 h-3.5 text-emerald-400 ${
              isSummaryLoading || isTxLoading ? "animate-spin" : ""
            }`}
          />
          Sync Data
        </button>
      </div>

      {/* Main Grid: Balance and Address Cards */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        <div className="lg:col-span-2">
          <BalanceCard
            summary={summary || null}
            isLoading={isSummaryLoading}
            isError={isSummaryError}
            error={summaryError as Error}
            onRefresh={handleManualRefresh}
          />
        </div>
        <div className="lg:col-span-1">
          <AddressCard
            address={summary?.address || wallet?.address || (isSummaryLoading ? "Loading..." : "")}
            publicKey={summary?.public_key}
          />
        </div>
      </div>

      {/* Recent Transactions Section */}
      <div className="rounded-2xl glass-panel p-6 border border-slate-800 shadow-xl space-y-4">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-2.5">
            <div className="p-2 rounded-lg bg-cyan-500/10 text-cyan-400 border border-cyan-500/20">
              <History className="w-4 h-4" />
            </div>
            <div>
              <h2 className="text-base font-bold text-white tracking-tight">Transaction History</h2>
              <p className="text-xs text-slate-400">Recent confirmed and pending mempool transfers</p>
            </div>
          </div>

          <Link
            to="/app/send"
            className="text-xs text-emerald-400 hover:text-emerald-300 font-semibold flex items-center gap-1"
          >
            New Transfer
            <ArrowUpRight className="w-3.5 h-3.5" />
          </Link>
        </div>

        {/* List Content */}
        <div className="pt-2">
          {isTxLoading ? (
            <div className="space-y-3">
              {[1, 2, 3].map((n) => (
                <div
                  key={n}
                  className="h-20 rounded-xl bg-slate-900/60 border border-slate-800/80 animate-pulse"
                />
              ))}
            </div>
          ) : isTxError ? (
            <div className="p-6 rounded-xl bg-rose-500/10 border border-rose-500/20 text-center space-y-3">
              <AlertCircle className="w-6 h-6 text-rose-400 mx-auto" />
              <p className="text-xs text-rose-300">
                Failed to load transaction history: {(txError as Error)?.message || "Unknown error"}
              </p>
              <button
                type="button"
                onClick={() => refetchTx()}
                className="px-3 py-1.5 rounded-lg bg-rose-500/20 hover:bg-rose-500/30 text-rose-300 text-xs font-medium transition-colors"
              >
                Retry
              </button>
            </div>
          ) : transactions && transactions.length > 0 ? (
            <div className="space-y-2.5">
              {transactions.map((tx) => (
                <TransactionRow key={tx.txid} tx={tx} />
              ))}
            </div>
          ) : (
            <div className="py-12 text-center rounded-xl bg-slate-950/40 border border-slate-800/60 flex flex-col items-center justify-center gap-3">
              <div className="w-12 h-12 rounded-full bg-slate-900 flex items-center justify-center text-slate-600">
                <Inbox className="w-6 h-6" />
              </div>
              <div>
                <p className="text-sm font-semibold text-slate-300">No transactions yet</p>
                <p className="text-xs text-slate-500 mt-1 max-w-sm">
                  Receive coins or fund your wallet in the mining dashboard to make transfers.
                </p>
              </div>
              <Link
                to="/app/receive"
                className="mt-2 text-xs font-semibold px-4 py-2 rounded-xl bg-slate-800 hover:bg-slate-700 text-slate-200 transition-colors"
              >
                Show Receive Address
              </Link>
            </div>
          )}
        </div>
      </div>
    </div>
  );
};
