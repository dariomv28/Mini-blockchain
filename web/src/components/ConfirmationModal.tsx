import React from "react";
import { AlertCircle, ArrowRight, ShieldCheck, X } from "lucide-react";

interface ConfirmationModalProps {
  isOpen: boolean;
  onClose: () => void;
  onConfirm: () => void;
  recipient: string;
  amount: number;
  fee: number;
  availableBalance: number;
  isSubmitting: boolean;
}

export const ConfirmationModal: React.FC<ConfirmationModalProps> = ({
  isOpen,
  onClose,
  onConfirm,
  recipient,
  amount,
  fee,
  availableBalance,
  isSubmitting,
}) => {
  if (!isOpen) return null;

  const totalDebit = amount + fee;
  const isExceeding = totalDebit > availableBalance;

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/75 backdrop-blur-sm animate-fadeIn">
      <div className="relative w-full max-w-md bg-slate-900 border border-slate-700/80 rounded-2xl shadow-2xl p-6 overflow-hidden">
        {/* Background glow accent */}
        <div className="absolute -top-12 -right-12 w-36 h-36 bg-emerald-500/10 rounded-full blur-3xl pointer-events-none" />

        <div className="flex items-center justify-between pb-4 border-b border-slate-800">
          <div className="flex items-center gap-2.5">
            <div className="p-2 rounded-lg bg-emerald-500/10 text-emerald-400 border border-emerald-500/20">
              <ShieldCheck className="w-5 h-5" />
            </div>
            <h3 className="text-lg font-bold text-white tracking-tight">Confirm Transaction</h3>
          </div>
          <button
            type="button"
            onClick={onClose}
            disabled={isSubmitting}
            className="p-1 text-slate-400 hover:text-white rounded-lg hover:bg-slate-800 transition-colors"
          >
            <X className="w-5 h-5" />
          </button>
        </div>

        <div className="py-5 space-y-4 text-sm">
          <div className="bg-slate-950/60 p-3.5 rounded-xl border border-slate-800/80 space-y-1">
            <span className="text-xs font-semibold text-slate-400 uppercase tracking-wider">Recipient Address</span>
            <div className="font-mono text-xs text-slate-200 break-all select-all">
              {recipient}
            </div>
          </div>

          <div className="bg-slate-950/60 p-4 rounded-xl border border-slate-800/80 space-y-2.5">
            <div className="flex justify-between items-center text-slate-300">
              <span>Send Amount</span>
              <span className="font-mono font-semibold text-white">{amount.toLocaleString()} PYC</span>
            </div>
            <div className="flex justify-between items-center text-slate-400 text-xs">
              <span>Estimated Network Fee</span>
              <span className="font-mono text-slate-300">{fee.toLocaleString()} PYC</span>
            </div>
            <div className="pt-2 border-t border-slate-800 flex justify-between items-center font-medium">
              <span className="text-slate-200">Total Debit</span>
              <span className="font-mono text-emerald-400 font-bold text-base">
                {totalDebit.toLocaleString()} PYC
              </span>
            </div>
          </div>

          {isExceeding && (
            <div className="p-3 bg-rose-500/10 border border-rose-500/20 rounded-xl flex items-start gap-2.5 text-rose-300 text-xs">
              <AlertCircle className="w-4 h-4 shrink-0 mt-0.5 text-rose-400" />
              <span>
                Total debit exceeds your available spendable balance ({availableBalance.toLocaleString()} PYC).
              </span>
            </div>
          )}

          <p className="text-xs text-slate-400 text-center">
            This transaction will be cryptographically signed by your wallet and submitted to the PyChain mempool.
          </p>
        </div>

        <div className="flex items-center gap-3 pt-2">
          <button
            type="button"
            onClick={onClose}
            disabled={isSubmitting}
            className="flex-1 px-4 py-2.5 rounded-xl border border-slate-700 bg-slate-800 text-slate-300 hover:bg-slate-700 hover:text-white text-sm font-medium transition-colors"
          >
            Cancel
          </button>
          <button
            type="button"
            onClick={onConfirm}
            disabled={isSubmitting || isExceeding}
            id="confirm-send-btn"
            className="flex-1 flex items-center justify-center gap-2 px-4 py-2.5 rounded-xl bg-gradient-to-r from-emerald-500 to-teal-600 hover:from-emerald-400 hover:to-teal-500 text-slate-950 font-bold text-sm shadow-lg shadow-emerald-500/20 disabled:opacity-50 disabled:cursor-not-allowed transition-all"
          >
            {isSubmitting ? (
              <>
                <div className="w-4 h-4 border-2 border-slate-950/20 border-t-slate-950 rounded-full animate-spin" />
                Signing...
              </>
            ) : (
              <>
                Send Now
                <ArrowRight className="w-4 h-4" />
              </>
            )}
          </button>
        </div>
      </div>
    </div>
  );
};
