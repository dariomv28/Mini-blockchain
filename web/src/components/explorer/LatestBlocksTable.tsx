import React from "react";
import { Link } from "react-router-dom";
import { Box, Clock } from "lucide-react";
import { ExplorerBlockListItem } from "../../types/explorer";
import { HashLink } from "./HashLink";

interface LatestBlocksTableProps {
  blocks: ExplorerBlockListItem[];
  isLoading?: boolean;
}

export const LatestBlocksTable: React.FC<LatestBlocksTableProps> = ({
  blocks,
  isLoading = false,
}) => {
  const formatTimeAgo = (timestamp: number) => {
    const elapsed = Math.floor(Date.now() / 1000) - timestamp;
    if (elapsed < 0) return "Just now";
    if (elapsed < 60) return `${elapsed}s ago`;
    if (elapsed < 3600) return `${Math.floor(elapsed / 60)}m ago`;
    if (elapsed < 86400) return `${Math.floor(elapsed / 3600)}h ago`;
    return `${Math.floor(elapsed / 86400)}d ago`;
  };

  if (isLoading) {
    return (
      <div className="bg-slate-900/70 border border-slate-800/80 rounded-2xl p-6 backdrop-blur-sm shadow-xl">
        <div className="h-6 w-36 bg-slate-800 rounded mb-4 animate-pulse" />
        <div className="space-y-3">
          {[...Array(5)].map((_, i) => (
            <div key={i} className="h-12 bg-slate-800/50 rounded-xl animate-pulse" />
          ))}
        </div>
      </div>
    );
  }

  return (
    <div className="bg-slate-900/70 border border-slate-800/80 rounded-2xl p-5 sm:p-6 backdrop-blur-sm shadow-xl">
      <div className="flex items-center justify-between pb-4 border-b border-slate-800 mb-4">
        <div className="flex items-center gap-2.5">
          <div className="w-8 h-8 rounded-lg bg-emerald-500/10 border border-emerald-500/30 flex items-center justify-center text-emerald-400">
            <Box className="w-4 h-4" />
          </div>
          <div>
            <h2 className="font-bold text-base text-white">Latest Blocks</h2>
            <p className="text-xs text-slate-400">Recently verified blocks on PyChain</p>
          </div>
        </div>
      </div>

      <div className="overflow-x-auto">
        <table className="w-full text-left border-collapse">
          <thead>
            <tr className="border-b border-slate-800 text-[11px] font-semibold text-slate-400 uppercase tracking-wider">
              <th className="py-2.5 px-3">Height</th>
              <th className="py-2.5 px-3">Age</th>
              <th className="py-2.5 px-3">Transactions</th>
              <th className="py-2.5 px-3">Size</th>
              <th className="py-2.5 px-3">Miner</th>
              <th className="py-2.5 px-3 text-right">Difficulty</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-slate-800/50 text-xs">
            {blocks.map((b) => (
              <tr
                key={b.hash}
                className="hover:bg-slate-800/40 transition-colors group"
              >
                {/* Height */}
                <td className="py-3 px-3">
                  <Link
                    to={`/explorer/block/${b.height}`}
                    className="font-mono font-bold text-emerald-400 hover:text-emerald-300 hover:underline flex items-center gap-1.5"
                  >
                    <span>#{b.height}</span>
                  </Link>
                </td>

                {/* Age / Time */}
                <td className="py-3 px-3 text-slate-400 flex items-center gap-1">
                  <Clock className="w-3.5 h-3.5 text-slate-500" />
                  <span>{formatTimeAgo(b.timestamp)}</span>
                </td>

                {/* Tx Count */}
                <td className="py-3 px-3 font-mono text-slate-200">
                  <span className="px-2 py-0.5 rounded bg-slate-800 border border-slate-700 text-slate-300 font-semibold">
                    {b.transaction_count} txs
                  </span>
                </td>

                {/* Size */}
                <td className="py-3 px-3 font-mono text-slate-400">
                  {b.size_bytes.toLocaleString()} bytes
                </td>

                {/* Miner */}
                <td className="py-3 px-3 font-mono">
                  {b.miner_address ? (
                    <HashLink value={b.miner_address} type="address" truncateLength={6} />
                  ) : (
                    <span className="text-slate-500 text-[11px]">Genesis</span>
                  )}
                </td>

                {/* Difficulty */}
                <td className="py-3 px-3 text-right font-mono text-slate-300">
                  {b.difficulty}
                </td>
              </tr>
            ))}
          </tbody>
        </table>

        {blocks.length === 0 && (
          <div className="py-8 text-center text-slate-500 text-xs">
            No blocks found in blockchain.
          </div>
        )}
      </div>
    </div>
  );
};
