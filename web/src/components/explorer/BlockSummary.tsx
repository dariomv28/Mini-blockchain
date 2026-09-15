import React from "react";
import { Box } from "lucide-react";
import { ExplorerBlockDetail } from "../../types/explorer";
import { HashLink } from "./HashLink";

interface BlockSummaryProps {
  block: ExplorerBlockDetail;
}

export const BlockSummary: React.FC<BlockSummaryProps> = ({ block }) => {
  const isGenesis =
    block.height === 0 ||
    block.previous_block_hash === "0".repeat(64);

  return (
    <div className="bg-slate-900/80 border border-slate-800/90 rounded-2xl p-6 backdrop-blur-sm shadow-xl">
      {/* Header */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between pb-5 border-b border-slate-800 gap-3">
        <div className="flex items-center gap-3">
          <div className="w-10 h-10 rounded-xl bg-emerald-500/10 border border-emerald-500/30 flex items-center justify-center text-emerald-400">
            <Box className="w-5 h-5" />
          </div>
          <div>
            <h1 className="text-xl sm:text-2xl font-black text-white flex items-center gap-2">
              Block #{block.height}
              <span className="text-xs font-mono font-bold px-2 py-0.5 rounded-full bg-emerald-500/10 text-emerald-400 border border-emerald-500/30">
                Confirmed
              </span>
            </h1>
            <p className="text-xs text-slate-400">
              Verified Proof-of-Work block on PyChain active chain
            </p>
          </div>
        </div>

        <div className="text-right font-mono text-xs text-slate-400">
          <span>Total Output: </span>
          <strong className="text-emerald-400 font-bold text-sm">
            {block.total_output_amount} PYC
          </strong>
        </div>
      </div>

      {/* Details Grid */}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-y-4 gap-x-8 mt-5 text-xs font-mono">
        {/* Hash */}
        <div>
          <span className="text-slate-400 block mb-1">Block Hash</span>
          <HashLink value={block.hash} type="block" truncate={false} className="break-all font-semibold" />
        </div>

        {/* Previous Block Hash */}
        <div>
          <span className="text-slate-400 block mb-1">Previous Hash</span>
          {isGenesis ? (
            <span className="text-slate-500 italic">00000000... (Genesis Block)</span>
          ) : (
            <HashLink
              value={block.previous_block_hash}
              type="block"
              truncate={false}
              className="break-all text-cyan-400"
            />
          )}
        </div>

        {/* Merkle Root */}
        <div>
          <span className="text-slate-400 block mb-1">Merkle Root</span>
          <span className="text-slate-200 break-all">{block.merkle_root}</span>
        </div>

        {/* Miner Address */}
        <div>
          <span className="text-slate-400 block mb-1">Miner / Coinbase Recipient</span>
          {block.miner_address ? (
            <HashLink value={block.miner_address} type="address" truncate={false} className="break-all" />
          ) : (
            <span className="text-slate-500">None (Genesis)</span>
          )}
        </div>

        {/* Timestamp */}
        <div>
          <span className="text-slate-400 block mb-1">Timestamp</span>
          <span className="text-slate-200">
            {new Date(block.timestamp * 1000).toUTCString()} ({block.timestamp})
          </span>
        </div>

        {/* Difficulty & Nonce */}
        <div className="flex items-center gap-6">
          <div>
            <span className="text-slate-400 block mb-1">Difficulty</span>
            <span className="text-slate-200">{block.difficulty}</span>
          </div>
          <div>
            <span className="text-slate-400 block mb-1">Nonce</span>
            <span className="text-amber-400 font-bold">{block.nonce.toLocaleString()}</span>
          </div>
          <div>
            <span className="text-slate-400 block mb-1">Block Size</span>
            <span className="text-slate-300">{block.size_bytes.toLocaleString()} bytes</span>
          </div>
        </div>

        {/* Transaction Count & Fees */}
        <div className="flex items-center gap-6">
          <div>
            <span className="text-slate-400 block mb-1">Transactions</span>
            <span className="text-emerald-400 font-bold">{block.transaction_count}</span>
          </div>
          <div>
            <span className="text-slate-400 block mb-1">Total Miner Fees</span>
            <span className="text-cyan-400 font-bold">+{block.total_fees} PYC</span>
          </div>
        </div>
      </div>
    </div>
  );
};
