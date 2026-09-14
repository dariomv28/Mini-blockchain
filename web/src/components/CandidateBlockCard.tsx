import React, { useState } from "react";
import { CandidateTemplate } from "../types/mining";
import { Box, Check, Coins, Copy, Cpu, Hammer, RefreshCw } from "lucide-react";

interface CandidateBlockCardProps {
  template: CandidateTemplate | null;
  isLoadingTemplate: boolean;
  isMiningActive: boolean;
  isStartingJob?: boolean;
  onBuildTemplate: () => void;
  onStartMining: () => void;
}

export const CandidateBlockCard: React.FC<CandidateBlockCardProps> = ({
  template,
  isLoadingTemplate,
  isMiningActive,
  isStartingJob = false,
  onBuildTemplate,
  onStartMining,
}) => {
  const [copiedField, setCopiedField] = useState<string | null>(null);

  const copyToClipboard = (text: string, field: string) => {
    navigator.clipboard.writeText(text);
    setCopiedField(field);
    setTimeout(() => setCopiedField(null), 2000);
  };

  return (
    <div className="bg-slate-900/70 border border-slate-800/80 rounded-2xl p-6 backdrop-blur-sm shadow-xl flex flex-col justify-between">
      {/* Card Header */}
      <div>
        <div className="flex items-center justify-between pb-4 border-b border-slate-800">
          <div className="flex items-center gap-3">
            <div className="w-9 h-9 rounded-xl bg-amber-500/10 border border-amber-500/20 flex items-center justify-center text-amber-400">
              <Box className="w-5 h-5" />
            </div>
            <div>
              <h3 className="font-bold text-base text-white flex items-center gap-2">
                Candidate Block
                {template && (
                  <span className="text-xs px-2 py-0.5 rounded-full bg-amber-500/10 text-amber-400 border border-amber-500/30 font-mono">
                    Height #{template.template_height}
                  </span>
                )}
              </h3>
              <p className="text-xs text-slate-400">
                Detached block blueprint assembled for Proof-of-Work mining
              </p>
            </div>
          </div>

          <button
            onClick={onBuildTemplate}
            disabled={isLoadingTemplate || isMiningActive}
            className="flex items-center gap-1.5 text-xs font-semibold px-3 py-1.5 rounded-lg bg-slate-800 hover:bg-slate-700 text-slate-200 border border-slate-700 transition-all disabled:opacity-50"
            title="Rebuild candidate block from latest chain tip"
          >
            <RefreshCw className={`w-3.5 h-3.5 ${isLoadingTemplate ? "animate-spin text-amber-400" : ""}`} />
            {isLoadingTemplate ? "Building..." : "Rebuild Template"}
          </button>
        </div>

        {/* Card Body */}
        {template ? (
          <div className="mt-5 space-y-4">
            {/* Previous Hash & Merkle Root */}
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
              <div className="bg-slate-950/60 border border-slate-800/60 rounded-xl p-3">
                <span className="text-[11px] uppercase tracking-wider text-slate-400 font-semibold block mb-1">
                  Previous Block Hash (Parent)
                </span>
                <div className="flex items-center justify-between font-mono text-xs text-slate-200">
                  <span className="truncate mr-2 font-medium">
                    {template.previous_block_hash.slice(0, 14)}...{template.previous_block_hash.slice(-8)}
                  </span>
                  <button
                    onClick={() => copyToClipboard(template.previous_block_hash, "prev_hash")}
                    className="text-slate-400 hover:text-white p-1 rounded transition-colors"
                  >
                    {copiedField === "prev_hash" ? (
                      <Check className="w-3.5 h-3.5 text-emerald-400" />
                    ) : (
                      <Copy className="w-3.5 h-3.5" />
                    )}
                  </button>
                </div>
              </div>

              <div className="bg-slate-950/60 border border-slate-800/60 rounded-xl p-3">
                <span className="text-[11px] uppercase tracking-wider text-slate-400 font-semibold block mb-1">
                  Merkle Root
                </span>
                <div className="flex items-center justify-between font-mono text-xs text-slate-200">
                  <span className="truncate mr-2 font-medium">
                    {template.merkle_root.slice(0, 14)}...{template.merkle_root.slice(-8)}
                  </span>
                  <button
                    onClick={() => copyToClipboard(template.merkle_root, "merkle_root")}
                    className="text-slate-400 hover:text-white p-1 rounded transition-colors"
                  >
                    {copiedField === "merkle_root" ? (
                      <Check className="w-3.5 h-3.5 text-emerald-400" />
                    ) : (
                      <Copy className="w-3.5 h-3.5" />
                    )}
                  </button>
                </div>
              </div>
            </div>

            {/* Difficulty, Target, & Recipient */}
            <div className="grid grid-cols-3 gap-3">
              <div className="bg-slate-950/60 border border-slate-800/60 rounded-xl p-3">
                <span className="text-[11px] uppercase tracking-wider text-slate-400 font-semibold block mb-1">
                  Difficulty
                </span>
                <span className="font-mono text-base font-bold text-amber-400">
                  {template.difficulty} bits
                </span>
              </div>

              <div className="bg-slate-950/60 border border-slate-800/60 rounded-xl p-3">
                <span className="text-[11px] uppercase tracking-wider text-slate-400 font-semibold block mb-1">
                  Transactions
                </span>
                <span className="font-mono text-base font-bold text-slate-200">
                  {template.transaction_count} txs
                </span>
              </div>

              <div className="bg-slate-950/60 border border-slate-800/60 rounded-xl p-3">
                <span className="text-[11px] uppercase tracking-wider text-slate-400 font-semibold block mb-1">
                  Initial Nonce
                </span>
                <span className="font-mono text-base font-bold text-slate-200">
                  0
                </span>
              </div>
            </div>

            {/* Recipient Address */}
            <div className="bg-slate-950/60 border border-slate-800/60 rounded-xl p-3 flex items-center justify-between">
              <div className="min-w-0 mr-2">
                <span className="text-[11px] uppercase tracking-wider text-slate-400 font-semibold block mb-0.5">
                  Miner Reward Destination (Your Wallet)
                </span>
                <span className="font-mono text-xs text-emerald-400 font-medium truncate block">
                  {template.miner_address}
                </span>
              </div>
              <button
                onClick={() => copyToClipboard(template.miner_address, "miner_address")}
                className="text-slate-400 hover:text-white p-1 rounded transition-colors flex-shrink-0"
              >
                {copiedField === "miner_address" ? (
                  <Check className="w-3.5 h-3.5 text-emerald-400" />
                ) : (
                  <Copy className="w-3.5 h-3.5" />
                )}
              </button>
            </div>

            {/* Reward Breakdown Banner */}
            <div className="bg-gradient-to-r from-emerald-950/40 via-slate-900/60 to-cyan-950/40 border border-emerald-500/30 rounded-xl p-4 flex flex-col sm:flex-row sm:items-center justify-between gap-3">
              <div className="flex items-center gap-3">
                <div className="w-10 h-10 rounded-xl bg-emerald-500/20 border border-emerald-500/30 flex items-center justify-center text-emerald-400">
                  <Coins className="w-5 h-5" />
                </div>
                <div>
                  <span className="text-xs text-slate-400 font-semibold">Estimated Block Reward</span>
                  <div className="flex items-center gap-2 text-xs font-mono">
                    <span className="text-slate-300">Subsidy: <strong>50 PYC</strong></span>
                    <span className="text-slate-500">+</span>
                    <span className="text-slate-300">Fees: <strong>{template.fees} PYC</strong></span>
                  </div>
                </div>
              </div>

              <div className="text-right">
                <span className="text-xl sm:text-2xl font-black font-mono text-transparent bg-clip-text bg-gradient-to-r from-emerald-400 to-cyan-400">
                  +{template.total_reward} PYC
                </span>
              </div>
            </div>
          </div>
        ) : isLoadingTemplate ? (
          <div className="py-16 text-center text-slate-400">
            <RefreshCw className="w-8 h-8 mx-auto mb-3 animate-spin text-amber-400" />
            <p className="text-sm font-semibold text-slate-200">Generating Candidate Block...</p>
            <p className="text-xs text-slate-500 mt-1">Connecting to blockchain node &amp; mempool</p>
          </div>
        ) : (
          <div className="py-12 text-center text-slate-500">
            <Cpu className="w-8 h-8 mx-auto mb-2 opacity-50" />
            <p className="text-sm">Click "Rebuild Template" to generate candidate block.</p>
          </div>
        )}
      </div>

      {/* Action Footer */}
      <div className="mt-6 pt-4 border-t border-slate-800 flex justify-end">
        <button
          onClick={onStartMining}
          disabled={!template || isMiningActive || isLoadingTemplate || isStartingJob}
          className="w-full sm:w-auto px-6 py-3 rounded-xl font-bold text-sm flex items-center justify-center gap-2.5 transition-all shadow-lg bg-gradient-to-r from-emerald-500 to-teal-600 hover:from-emerald-400 hover:to-teal-500 text-slate-950 font-black shadow-emerald-500/20 disabled:opacity-40 disabled:cursor-not-allowed cursor-pointer"
        >
          <Hammer className={`w-4 h-4 ${isMiningActive ? "animate-bounce" : ""}`} />
          {isStartingJob ? "Starting Job..." : isMiningActive ? "Mining in Progress..." : "Mine This Block"}
        </button>
      </div>
    </div>
  );
};
