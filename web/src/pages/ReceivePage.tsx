import React from "react";
import { Link } from "react-router-dom";
import { useAuth } from "../auth/AuthContext";
import { QRCodeDisplay } from "../components/QRCodeDisplay";
import { CopyButton } from "../components/CopyButton";
import { ArrowDownLeft, ArrowLeft, Info, Wallet } from "lucide-react";

export const ReceivePage: React.FC = () => {
  const { wallet, user } = useAuth();
  const address = wallet?.address || "";

  return (
    <div className="max-w-xl mx-auto space-y-6 animate-fadeIn">
      <Link
        to="/app"
        className="inline-flex items-center gap-2 text-xs font-semibold text-slate-400 hover:text-white transition-colors"
      >
        <ArrowLeft className="w-4 h-4" />
        Back to Dashboard
      </Link>

      <div className="rounded-2xl glass-panel p-6 sm:p-8 border border-slate-800 shadow-2xl relative overflow-hidden text-center">
        {/* Glow orb */}
        <div className="absolute top-0 left-1/2 -translate-x-1/2 w-72 h-72 bg-cyan-500/10 rounded-full blur-3xl pointer-events-none" />

        <div className="flex items-center justify-center gap-3 mb-6 pb-4 border-b border-slate-800">
          <div className="p-2.5 rounded-xl bg-cyan-500/10 text-cyan-400 border border-cyan-500/20">
            <ArrowDownLeft className="w-5 h-5 stroke-[2.5]" />
          </div>
          <div className="text-left">
            <h1 className="text-xl font-bold text-white tracking-tight">Receive PYC Coins</h1>
            <p className="text-xs text-slate-400">Share your public address to receive transfers</p>
          </div>
        </div>

        {/* QR Code container */}
        <div className="my-6 flex justify-center">
          <QRCodeDisplay value={address} size={200} />
        </div>

        {/* Address display box */}
        <div className="p-4 rounded-xl bg-slate-950/80 border border-slate-800 space-y-2 text-left">
          <div className="flex items-center justify-between text-xs font-semibold uppercase tracking-wider text-slate-400">
            <span className="flex items-center gap-1.5 text-cyan-400">
              <Wallet className="w-3.5 h-3.5" />
              Your PyChain Address
            </span>
            <span className="text-slate-500 text-[11px]">Owner: {user?.username}</span>
          </div>

          <div className="p-2.5 rounded-lg bg-slate-900 border border-slate-800/90 font-mono text-xs text-slate-200 break-all select-all">
            {address}
          </div>

          <div className="pt-2 flex justify-end">
            <CopyButton text={address} label="Copy Full Address" className="px-3 py-1.5 text-xs" />
          </div>
        </div>

        {/* Instructions note */}
        <div className="mt-6 p-4 rounded-xl bg-slate-900/50 border border-slate-800/80 text-left space-y-2 text-xs text-slate-400">
          <div className="flex items-center gap-2 text-slate-300 font-semibold">
            <Info className="w-4 h-4 text-emerald-400 shrink-0" />
            <span>How incoming transfers work</span>
          </div>
          <p>
            • Provide this address to the sender.
          </p>
          <p>
            • When broadcasted, the transaction will appear as <span className="text-amber-400 font-semibold">Pending</span> in your Recent Transactions list.
          </p>
          <p>
            • Once mined into a block, the transaction updates to <span className="text-emerald-400 font-semibold">Confirmed</span> and becomes part of your spendable balance.
          </p>
        </div>
      </div>
    </div>
  );
};
