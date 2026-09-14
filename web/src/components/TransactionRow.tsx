import React from "react";
import { TransactionItem } from "../types/api";
import { DirectionBadge, StatusBadge } from "./StatusBadge";
import { CopyButton } from "./CopyButton";
import { Blocks, Layers } from "lucide-react";

interface TransactionRowProps {
  tx: TransactionItem;
}

export const TransactionRow: React.FC<TransactionRowProps> = ({ tx }) => {
  const isSent = tx.direction === "sent";
  const dateFormatted = new Date(tx.timestamp * 1000).toLocaleString(undefined, {
    month: "short",
    day: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  });

  return (
    <div className="p-4 rounded-xl glass-panel glass-panel-hover border border-slate-800/80 flex flex-col sm:flex-row sm:items-center justify-between gap-3">
      {/* Left side: direction icon & meta */}
      <div className="flex items-center gap-3">
        <div className="flex flex-col gap-1.5">
          <div className="flex items-center gap-2">
            <DirectionBadge direction={tx.direction} />
            <StatusBadge status={tx.status} />
          </div>

          <div className="flex items-center gap-2 text-xs text-slate-400 font-mono">
            <span title={tx.txid}>
              TX: {tx.txid.slice(0, 8)}...{tx.txid.slice(-6)}
            </span>
            <CopyButton text={tx.txid} className="py-0.5 px-1.5 text-[10px]" />
          </div>
        </div>
      </div>

      {/* Right side: amount, block, timestamp */}
      <div className="flex sm:flex-col items-end justify-between sm:justify-center gap-1 border-t sm:border-t-0 border-slate-800/60 pt-2 sm:pt-0">
        <span
          className={`font-mono font-bold text-base ${
            isSent ? "text-rose-400" : "text-emerald-400"
          }`}
        >
          {isSent ? "-" : "+"}
          {tx.amount.toLocaleString()} PYC
        </span>

        <div className="flex items-center gap-3 text-xs text-slate-500">
          <span className="flex items-center gap-1">
            {tx.block_height !== null ? (
              <>
                <Blocks className="w-3 h-3 text-slate-400" />
                <span className="text-slate-300">#{tx.block_height}</span>
              </>
            ) : (
              <>
                <Layers className="w-3 h-3 text-amber-400 animate-pulse" />
                <span className="text-amber-400 font-medium">Mempool</span>
              </>
            )}
          </span>
          <span>•</span>
          <span title={new Date(tx.timestamp * 1000).toISOString()}>{dateFormatted}</span>
        </div>
      </div>
    </div>
  );
};
