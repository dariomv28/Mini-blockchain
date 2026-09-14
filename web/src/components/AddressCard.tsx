import React from "react";
import { Key, QrCode, Wallet } from "lucide-react";
import { Link } from "react-router-dom";
import { CopyButton } from "./CopyButton";

interface AddressCardProps {
  address: string;
  publicKey?: string;
}

export const AddressCard: React.FC<AddressCardProps> = ({ address, publicKey }) => {
  return (
    <div className="rounded-2xl glass-panel p-5 border border-slate-800 shadow-xl space-y-3.5">
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2 text-xs font-semibold uppercase tracking-wider text-slate-400">
          <Wallet className="w-3.5 h-3.5 text-cyan-400" />
          Custodial Wallet Address
        </div>
        <Link
          to="/app/receive"
          className="inline-flex items-center gap-1 text-xs text-cyan-400 hover:text-cyan-300 font-medium transition-colors"
        >
          <QrCode className="w-3.5 h-3.5" />
          QR Code
        </Link>
      </div>

      <div className="flex items-center justify-between gap-3 p-3 rounded-xl bg-slate-950/60 border border-slate-800/80">
        <span
          className="font-mono text-xs sm:text-sm text-slate-200 truncate select-all"
          title={address}
        >
          {address}
        </span>
        <CopyButton text={address} label="Copy" />
      </div>

      {publicKey && (
        <div className="flex items-center justify-between text-xs text-slate-500 pt-1">
          <span className="flex items-center gap-1">
            <Key className="w-3 h-3 text-slate-600" />
            Public Key
          </span>
          <span className="font-mono text-slate-400 truncate max-w-[200px]" title={publicKey}>
            {publicKey.slice(0, 10)}...{publicKey.slice(-8)}
          </span>
        </div>
      )}
    </div>
  );
};
