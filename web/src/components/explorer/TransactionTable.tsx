import { Coins, Send } from "lucide-react";
import { EnrichedTransaction } from "../../types/explorer";
import { HashLink } from "./HashLink";

interface TransactionTableProps {
  transactions: EnrichedTransaction[];
  showStatus?: boolean;
}

export const TransactionTable: React.FC<TransactionTableProps> = ({
  transactions,
  showStatus = false,
}) => {
  if (transactions.length === 0) {
    return (
      <div className="py-8 text-center text-slate-500 text-xs">
        No transactions in this block or record.
      </div>
    );
  }

  return (
    <div className="space-y-4">
      {transactions.map((tx) => {
        const totalOutput = tx.outputs.reduce((acc, cur) => acc + cur.amount, 0);

        return (
          <div
            key={tx.txid}
            className="bg-slate-900/80 border border-slate-800/80 rounded-2xl p-4 sm:p-5 backdrop-blur-sm shadow-md hover:border-slate-700/80 transition-all"
          >
            {/* Top Bar: TxID + Status + Fee */}
            <div className="flex flex-col sm:flex-row sm:items-center justify-between pb-3 border-b border-slate-800/60 gap-2">
              <div className="flex items-center gap-2">
                {tx.is_coinbase ? (
                  <span className="flex items-center gap-1 text-[11px] font-bold px-2 py-0.5 rounded-full bg-amber-500/10 text-amber-400 border border-amber-500/30">
                    <Coins className="w-3 h-3" />
                    Coinbase
                  </span>
                ) : (
                  <span className="flex items-center gap-1 text-[11px] font-bold px-2 py-0.5 rounded-full bg-cyan-500/10 text-cyan-400 border border-cyan-500/30">
                    <Send className="w-3 h-3" />
                    Transfer
                  </span>
                )}

                <HashLink value={tx.txid} type="tx" truncateLength={10} className="font-bold text-sm" />
              </div>

              <div className="flex items-center gap-3 text-xs font-mono">
                {showStatus && (
                  <span
                    className={`px-2 py-0.5 rounded text-[11px] font-bold ${
                      tx.status === "confirmed"
                        ? "bg-emerald-500/10 text-emerald-400 border border-emerald-500/30"
                        : "bg-amber-500/10 text-amber-400 border border-amber-500/30 animate-pulse"
                    }`}
                  >
                    {tx.status === "confirmed"
                      ? tx.block_height !== null && tx.block_height !== undefined
                        ? `Block #${tx.block_height}`
                        : "Confirmed"
                      : "Pending"}
                  </span>
                )}

                <span className="text-slate-400">
                  Fee: <strong className="text-slate-200">{tx.fee} PYC</strong>
                </span>

                <span className="text-slate-400">
                  Total:{" "}
                  <strong className="text-emerald-400 font-bold">{totalOutput} PYC</strong>
                </span>
              </div>
            </div>

            {/* Inputs & Outputs Breakdown */}
            <div className="grid grid-cols-1 md:grid-cols-2 gap-4 mt-3 text-xs font-mono">
              {/* Inputs */}
              <div className="bg-slate-950/50 rounded-xl p-3 border border-slate-800/40">
                <span className="text-[11px] font-semibold text-slate-400 uppercase tracking-wider block mb-2">
                  Inputs ({tx.inputs.length})
                </span>
                {tx.is_coinbase ? (
                  <div className="text-amber-400/90 text-xs italic py-1">
                    Newly Generated Block Subsidy + Fees (No previous outputs)
                  </div>
                ) : (
                  <div className="space-y-1.5">
                    {tx.inputs.map((inp, idx) => (
                      <div
                        key={idx}
                        className="flex items-center justify-between text-slate-300"
                      >
                        {inp.source_address ? (
                          <HashLink value={inp.source_address} type="address" truncateLength={6} />
                        ) : (
                          <span className="text-slate-500">Unknown Outpoint</span>
                        )}
                        {inp.amount !== null && inp.amount !== undefined && (
                          <span className="text-slate-400 font-medium">
                            {inp.amount} PYC
                          </span>
                        )}
                      </div>
                    ))}
                  </div>
                )}
              </div>

              {/* Outputs */}
              <div className="bg-slate-950/50 rounded-xl p-3 border border-slate-800/40">
                <span className="text-[11px] font-semibold text-slate-400 uppercase tracking-wider block mb-2">
                  Outputs ({tx.outputs.length})
                </span>
                <div className="space-y-1.5">
                  {tx.outputs.map((out, idx) => (
                    <div
                      key={idx}
                      className="flex items-center justify-between text-slate-300"
                    >
                      <HashLink value={out.recipient_address} type="address" truncateLength={6} />
                      <span className="text-emerald-400 font-bold">
                        +{out.amount} PYC
                      </span>
                    </div>
                  ))}
                </div>
              </div>
            </div>
          </div>
        );
      })}
    </div>
  );
};
