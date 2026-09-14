import React from "react";
import { MempoolTransaction } from "../types/mining";
import { Clock, Copy, Check, Inbox, Layers, RefreshCw } from "lucide-react";

interface MempoolTableProps {
  transactions: MempoolTransaction[];
  isLoading?: boolean;
  onRefresh?: () => void;
}

export const MempoolTable: React.FC<MempoolTableProps> = ({
  transactions,
  isLoading = false,
  onRefresh,
}) => {
  const txList = Array.isArray(transactions) ? transactions : [];
  const [copiedTxid, setCopiedTxid] = React.useState<string | null>(null);

  const handleCopy = (txid: string) => {
    navigator.clipboard.writeText(txid);
    setCopiedTxid(txid);
    setTimeout(() => setCopiedTxid(null), 2000);
  };

  const totalFees = txList.reduce((acc, tx) => acc + (tx.fee || 0), 0);

  return (
    <div className="bg-slate-900/70 border border-slate-800/80 rounded-2xl p-6 backdrop-blur-sm shadow-xl flex flex-col h-full">
      {/* Header */}
      <div className="flex items-center justify-between pb-4 border-b border-slate-800">
        <div className="flex items-center gap-3">
          <div className="w-9 h-9 rounded-xl bg-cyan-500/10 border border-cyan-500/20 flex items-center justify-center text-cyan-400">
            <Layers className="w-5 h-5" />
          </div>
          <div>
            <h3 className="font-bold text-base text-white flex items-center gap-2">
              Memory Pool (Mempool)
              <span className="text-xs px-2 py-0.5 rounded-full bg-cyan-500/10 text-cyan-400 border border-cyan-500/30 font-mono">
                {txList.length} txs
              </span>
            </h3>
            <p className="text-xs text-slate-400">
              Unconfirmed transactions awaiting inclusion into a block
            </p>
          </div>
        </div>

        {onRefresh && (
          <button
            onClick={onRefresh}
            disabled={isLoading}
            title="Refresh Mempool"
            className="p-2 text-slate-400 hover:text-white rounded-lg hover:bg-slate-800 transition-colors disabled:opacity-50"
          >
            <RefreshCw className={`w-4 h-4 ${isLoading ? "animate-spin" : ""}`} />
          </button>
        )}
      </div>

      {/* Content */}
      <div className="flex-1 mt-4 overflow-hidden flex flex-col">
        {txList.length === 0 ? (
          <div className="flex-1 flex flex-col items-center justify-center py-10 text-center">
            <div className="w-12 h-12 rounded-2xl bg-slate-800/50 border border-slate-700/50 flex items-center justify-center text-slate-500 mb-3">
              <Inbox className="w-6 h-6 stroke-[1.5]" />
            </div>
            <p className="text-sm font-medium text-slate-300">Mempool is currently empty</p>
            <p className="text-xs text-slate-500 max-w-xs mt-1">
              There are no pending user transfers right now. Candidate block will include only the 50 PYC Coinbase subsidy reward.
            </p>
          </div>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-left text-xs">
              <thead className="text-[11px] uppercase tracking-wider text-slate-400 border-b border-slate-800">
                <tr>
                  <th className="py-2.5 px-3">Transaction ID</th>
                  <th className="py-2.5 px-3">Time</th>
                  <th className="py-2.5 px-3 text-right">Fee</th>
                  <th className="py-2.5 px-3 text-right">Total Out</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-800/60 font-mono">
                {txList.map((tx) => {
                  const outputTotal = (tx.outputs || []).reduce((sum, out) => sum + out.amount, 0);
                  return (
                    <tr key={tx.txid} className="hover:bg-slate-800/30 transition-colors">
                      <td className="py-2.5 px-3">
                        <div className="flex items-center gap-1.5">
                          <span className="text-slate-300 font-semibold truncate max-w-[120px] sm:max-w-[180px]">
                            {tx.txid.slice(0, 10)}...{tx.txid.slice(-8)}
                          </span>
                          <button
                            onClick={() => handleCopy(tx.txid)}
                            className="p-1 hover:text-white text-slate-500 transition-colors"
                            title="Copy TxID"
                          >
                            {copiedTxid === tx.txid ? (
                              <Check className="w-3.5 h-3.5 text-emerald-400" />
                            ) : (
                              <Copy className="w-3.5 h-3.5" />
                            )}
                          </button>
                        </div>
                      </td>
                      <td className="py-2.5 px-3 text-slate-400 flex items-center gap-1">
                        <Clock className="w-3 h-3 text-slate-500" />
                        {new Date(tx.timestamp * 1000).toLocaleTimeString()}
                      </td>
                      <td className="py-2.5 px-3 text-right text-emerald-400 font-semibold">
                        +{tx.fee ?? 0} PYC
                      </td>
                      <td className="py-2.5 px-3 text-right text-slate-200">
                        {outputTotal} PYC
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        )}
      </div>

      {/* Footer fee aggregate */}
      {txList.length > 0 && (
        <div className="pt-3 border-t border-slate-800/80 mt-auto flex items-center justify-between text-xs">
          <span className="text-slate-400">Total Pending Fees:</span>
          <span className="font-mono font-bold text-emerald-400">+{totalFees} PYC</span>
        </div>
      )}
    </div>
  );
};
