import React from "react";
import { Link } from "react-router-dom";
import { ExternalLink } from "lucide-react";
import { ExplorerUTXOItem } from "../../types/explorer";

interface UtxoTableProps {
  utxos: ExplorerUTXOItem[];
}

export const UtxoTable: React.FC<UtxoTableProps> = ({ utxos }) => {
  if (utxos.length === 0) {
    return (
      <div className="py-8 text-center text-slate-500 text-xs">
        No unspent outputs (UTXOs) currently held by this address.
      </div>
    );
  }

  return (
    <div className="overflow-x-auto">
      <table className="w-full text-left border-collapse text-xs font-mono">
        <thead>
          <tr className="border-b border-slate-800 text-[11px] font-semibold text-slate-400 uppercase tracking-wider">
            <th className="py-2.5 px-3">Outpoint (TxID:Index)</th>
            <th className="py-2.5 px-3 text-right">Amount</th>
          </tr>
        </thead>
        <tbody className="divide-y divide-slate-800/50">
          {utxos.map((u, i) => (
            <tr key={i} className="hover:bg-slate-800/40 transition-colors">
              <td className="py-2.5 px-3 text-slate-300">
                <Link
                  to={`/explorer/tx/${u.txid}`}
                  className="text-emerald-400 hover:text-emerald-300 hover:underline inline-flex items-center gap-1"
                >
                  <span>
                    {u.txid.slice(0, 10)}...{u.txid.slice(-8)}:{u.output_index}
                  </span>
                  <ExternalLink className="w-3 h-3 opacity-50" />
                </Link>
              </td>
              <td className="py-2.5 px-3 text-right font-bold text-emerald-400">
                +{u.amount} PYC
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
};
