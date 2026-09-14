import React, { useState } from "react";
import { Link } from "react-router-dom";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useAuth } from "../auth/AuthContext";
import * as walletApi from "../api/wallet";
import { ConfirmationModal } from "../components/ConfirmationModal";
import { CopyButton } from "../components/CopyButton";
import { AlertCircle, ArrowLeft, ArrowUpRight, CheckCircle2, Send, ShieldAlert, Sparkles } from "lucide-react";
import { ApiClientError } from "../api/client";

export const SendPage: React.FC = () => {
  const queryClient = useQueryClient();
  const { user } = useAuth();

  const { data: summary } = useQuery(["wallet", user?.id], walletApi.getWalletSummary, {
    enabled: !!user?.id,
    staleTime: 5000,
  });

  const availableBalance = summary?.available_balance ?? 0;

  const [recipient, setRecipient] = useState("");
  const [amount, setAmount] = useState<string>("");
  const [fee, setFee] = useState<string>("1");
  const [error, setError] = useState<string | null>(null);
  const [isModalOpen, setIsModalOpen] = useState(false);
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [txReceipt, setTxReceipt] = useState<{ txid: string; status: string } | null>(null);

  // Preserve Idempotency-Key for retries of the same transfer intent
  const [idempotencyKey, setIdempotencyKey] = useState<string>("");

  const handleBlockExponential = (e: React.KeyboardEvent<HTMLInputElement>) => {
    if (["e", "E", "+", "-", "."].includes(e.key)) {
      e.preventDefault();
    }
  };

  const handleRecipientChange = (val: string) => {
    setRecipient(val);
    setIdempotencyKey("");
  };

  const handleAmountChange = (val: string) => {
    setAmount(val);
    setIdempotencyKey("");
  };

  const handleFeeChange = (val: string) => {
    setFee(val);
    setIdempotencyKey("");
  };

  const cleanRecipient = recipient.trim();
  const cleanAmount = amount.trim();
  const cleanFee = fee.trim();

  // Strict integer checks without scientific notation or decimals
  const isAmountValid = /^[1-9]\d*$/.test(cleanAmount);
  const isFeeValid = /^(0|[1-9]\d*)$/.test(cleanFee);

  const numAmount = isAmountValid ? parseInt(cleanAmount, 10) : 0;
  const numFee = isFeeValid ? parseInt(cleanFee, 10) : 0;

  const handleOpenConfirm = (e: React.FormEvent) => {
    e.preventDefault();
    setError(null);

    if (!cleanRecipient.startsWith("PYC_") || cleanRecipient.length < 10) {
      setError("Recipient address must begin with 'PYC_' and be a valid PyChain address");
      return;
    }

    if (!isAmountValid) {
      setError("Please enter a valid positive whole number amount (exponential notation and decimals are not allowed)");
      return;
    }

    if (!isFeeValid) {
      setError("Please enter a valid non-negative whole number network fee (exponential notation and decimals are not allowed)");
      return;
    }

    const total = numAmount + numFee;
    if (total > availableBalance) {
      setError(
        `Insufficient available balance. Total needed: ${total.toLocaleString()} PYC (Available: ${availableBalance.toLocaleString()} PYC)`
      );
      return;
    }

    // Establish or reuse idempotency key for this transfer intent
    if (!idempotencyKey) {
      const newKey = `tx_${Date.now()}_${Math.random().toString(36).substring(2, 10)}`;
      setIdempotencyKey(newKey);
    }

    setIsModalOpen(true);
  };

  const handleConfirmSend = async () => {
    setIsSubmitting(true);
    setError(null);

    const activeKey = idempotencyKey || `tx_${Date.now()}_${Math.random().toString(36).substring(2, 10)}`;
    if (!idempotencyKey) {
      setIdempotencyKey(activeKey);
    }

    try {
      const res = await walletApi.sendTransaction(
        {
          recipient_address: cleanRecipient,
          amount: numAmount,
          fee: numFee,
        },
        activeKey
      );

      setTxReceipt(res);
      setIsModalOpen(false);
      setIdempotencyKey("");

      // Invalidate queries so dashboard and balances update
      queryClient.invalidateQueries(["wallet"]);
    } catch (err) {
      setIsModalOpen(false);
      if (err instanceof ApiClientError) {
        setError(err.message || "Failed to submit transaction to the network");
      } else {
        setError("Network communication error. You can safely retry without double-spending.");
      }
    } finally {
      setIsSubmitting(false);
    }
  };

  const handleResetForm = () => {
    setRecipient("");
    setAmount("");
    setFee("1");
    setIdempotencyKey("");
    setTxReceipt(null);
    setError(null);
  };

  const handleMaxAmount = () => {
    const currentFee = isFeeValid ? numFee : 1;
    const max = Math.max(0, availableBalance - currentFee);
    setAmount(max.toString());
    setIdempotencyKey("");
  };

  return (
    <div className="max-w-2xl mx-auto space-y-6 animate-fadeIn">
      {/* Back button */}
      <Link
        to="/app"
        className="inline-flex items-center gap-2 text-xs font-semibold text-slate-400 hover:text-white transition-colors"
      >
        <ArrowLeft className="w-4 h-4" />
        Back to Dashboard
      </Link>

      <div className="rounded-2xl glass-panel p-6 sm:p-8 border border-slate-800 shadow-2xl relative overflow-hidden">
        {/* Glow accent */}
        <div className="absolute top-0 right-0 w-80 h-80 bg-emerald-500/10 rounded-full blur-3xl pointer-events-none" />

        {txReceipt ? (
          /* Transaction Submitted Success Screen */
          <div className="space-y-6 text-center py-4 animate-fadeIn">
            <div className="inline-flex items-center justify-center w-16 h-16 rounded-2xl bg-emerald-500/20 text-emerald-400 border border-emerald-500/30 shadow-xl shadow-emerald-500/10">
              <CheckCircle2 className="w-9 h-9" />
            </div>

            <div>
              <h2 className="text-2xl font-bold text-white tracking-tight">Transaction Broadcasted!</h2>
              <p className="mt-1 text-xs text-slate-400">
                Your transaction has entered the mempool and will be confirmed in the next block.
              </p>
            </div>

            <div className="p-4 rounded-xl bg-slate-950/80 border border-slate-800 text-left space-y-3">
              <div>
                <span className="text-[11px] font-semibold text-slate-400 uppercase tracking-wider">
                  Transaction ID (TXID)
                </span>
                <div className="mt-1 flex items-center justify-between gap-2 p-2 rounded-lg bg-slate-900 border border-slate-800 font-mono text-xs text-slate-200 break-all select-all">
                  <span>{txReceipt.txid}</span>
                  <CopyButton text={txReceipt.txid} className="py-0.5 px-2 text-[10px]" />
                </div>
              </div>

              <div className="flex items-center justify-between text-xs pt-1">
                <span className="text-slate-400">Initial Status:</span>
                <span className="px-2.5 py-0.5 rounded-full text-xs font-semibold bg-amber-500/10 text-amber-400 border border-amber-500/30">
                  Pending Mempool
                </span>
              </div>
            </div>

            <div className="flex flex-col sm:flex-row items-center gap-3 pt-2">
              <button
                type="button"
                onClick={handleResetForm}
                className="w-full sm:w-1/2 py-2.5 px-4 rounded-xl bg-slate-800 hover:bg-slate-700 text-slate-200 font-semibold text-sm border border-slate-700 transition-colors"
              >
                Send Another Transfer
              </button>
              <Link
                to="/app"
                className="w-full sm:w-1/2 py-2.5 px-4 rounded-xl bg-gradient-to-r from-emerald-500 to-teal-600 hover:from-emerald-400 hover:to-teal-500 text-slate-950 font-bold text-sm shadow-lg shadow-emerald-500/20 text-center transition-all"
              >
                View in Dashboard
              </Link>
            </div>
          </div>
        ) : (
          /* Send Form */
          <>
            <div className="flex items-center gap-3 mb-6 pb-4 border-b border-slate-800">
              <div className="p-2.5 rounded-xl bg-emerald-500/10 text-emerald-400 border border-emerald-500/20">
                <Send className="w-5 h-5 stroke-[2.5]" />
              </div>
              <div>
                <h1 className="text-xl font-bold text-white tracking-tight">Send PYC Coins</h1>
                <p className="text-xs text-slate-400">
                  Transfer coins securely via UTXO coin selection
                </p>
              </div>
            </div>

            {error && (
              <div className="mb-6 p-3.5 rounded-xl bg-rose-500/10 border border-rose-500/20 flex items-start gap-3 text-rose-300 text-xs">
                <AlertCircle className="w-4 h-4 shrink-0 mt-0.5 text-rose-400" />
                <span>{error}</span>
              </div>
            )}

            <form onSubmit={handleOpenConfirm} className="space-y-5">
              {/* Recipient input */}
              <div>
                <label
                  htmlFor="send-recipient"
                  className="block text-xs font-semibold uppercase tracking-wider text-slate-400 mb-1.5"
                >
                  Recipient PyChain Address
                </label>
                <input
                  id="send-recipient"
                  type="text"
                  required
                  value={recipient}
                  onChange={(e) => handleRecipientChange(e.target.value)}
                  placeholder="PYC_..."
                  className="w-full px-4 py-2.5 bg-slate-950/80 border border-slate-700/80 rounded-xl text-sm font-mono text-white placeholder-slate-500 focus:outline-none focus:border-emerald-500 focus:ring-1 focus:ring-emerald-500 transition-colors"
                />
              </div>

              {/* Amount input with Max button */}
              <div>
                <div className="flex justify-between items-center mb-1.5">
                  <label
                    htmlFor="send-amount"
                    className="block text-xs font-semibold uppercase tracking-wider text-slate-400"
                  >
                    Amount (PYC)
                  </label>
                  <div className="flex items-center gap-2 text-xs">
                    <span className="text-slate-400">
                      Available:{" "}
                      <span className="font-mono text-emerald-400 font-bold">
                        {availableBalance.toLocaleString()} PYC
                      </span>
                    </span>
                    <button
                      type="button"
                      onClick={handleMaxAmount}
                      id="max-amount-btn"
                      className="px-1.5 py-0.5 rounded bg-emerald-500/10 hover:bg-emerald-500/20 text-emerald-400 border border-emerald-500/30 text-[10px] font-bold uppercase transition-colors"
                    >
                      Max
                    </button>
                  </div>
                </div>

                <div className="relative">
                  <input
                    id="send-amount"
                    type="number"
                    min="1"
                    step="1"
                    required
                    value={amount}
                    onKeyDown={handleBlockExponential}
                    onChange={(e) => handleAmountChange(e.target.value)}
                    placeholder="0"
                    className="w-full pl-4 pr-14 py-2.5 bg-slate-950/80 border border-slate-700/80 rounded-xl text-sm font-mono text-white placeholder-slate-500 focus:outline-none focus:border-emerald-500 focus:ring-1 focus:ring-emerald-500 transition-colors"
                  />
                  <div className="absolute inset-y-0 right-0 pr-4 flex items-center pointer-events-none text-xs font-bold text-slate-500">
                    PYC
                  </div>
                </div>
              </div>

              {/* Fee input */}
              <div>
                <div className="flex justify-between items-center mb-1.5">
                  <label
                    htmlFor="send-fee"
                    className="block text-xs font-semibold uppercase tracking-wider text-slate-400"
                  >
                    Miner Fee (PYC)
                  </label>
                  <span className="text-[11px] text-slate-500 flex items-center gap-1">
                    <Sparkles className="w-3 h-3 text-cyan-400" />
                    Prioritizes mempool inclusion
                  </span>
                </div>
                <div className="relative">
                  <input
                    id="send-fee"
                    type="number"
                    min="0"
                    step="1"
                    required
                    value={fee}
                    onKeyDown={handleBlockExponential}
                    onChange={(e) => handleFeeChange(e.target.value)}
                    placeholder="1"
                    className="w-full pl-4 pr-14 py-2.5 bg-slate-950/80 border border-slate-700/80 rounded-xl text-sm font-mono text-white placeholder-slate-500 focus:outline-none focus:border-emerald-500 focus:ring-1 focus:ring-emerald-500 transition-colors"
                  />
                  <div className="absolute inset-y-0 right-0 pr-4 flex items-center pointer-events-none text-xs font-bold text-slate-500">
                    PYC
                  </div>
                </div>
              </div>

              {/* Summary box */}
              {isAmountValid && numAmount > 0 && (
                <div className="p-4 rounded-xl bg-slate-950/40 border border-slate-800/80 space-y-2 text-xs">
                  <div className="flex justify-between text-slate-400">
                    <span>Transfer Amount:</span>
                    <span className="font-mono text-slate-200">{numAmount.toLocaleString()} PYC</span>
                  </div>
                  <div className="flex justify-between text-slate-400">
                    <span>Network Fee:</span>
                    <span className="font-mono text-slate-200">
                      {numFee.toLocaleString()} PYC
                    </span>
                  </div>
                  <div className="pt-2 border-t border-slate-800 flex justify-between font-bold text-sm">
                    <span className="text-white">Estimated Debit:</span>
                    <span className="font-mono text-emerald-400">
                      {(numAmount + numFee).toLocaleString()} PYC
                    </span>
                  </div>
                </div>
              )}

              {availableBalance === 0 && (
                <div className="p-3 bg-amber-500/10 border border-amber-500/20 rounded-xl flex items-start gap-2.5 text-amber-300 text-xs">
                  <ShieldAlert className="w-4 h-4 shrink-0 mt-0.5 text-amber-400" />
                  <span>
                    Your available balance is currently 0 PYC. You cannot send transactions until your address receives or mines coins.
                  </span>
                </div>
              )}

              <button
                type="submit"
                id="review-transaction-btn"
                disabled={availableBalance === 0}
                className="w-full flex items-center justify-center gap-2 py-3 px-4 rounded-xl bg-gradient-to-r from-emerald-500 to-teal-600 hover:from-emerald-400 hover:to-teal-500 text-slate-950 font-bold text-sm shadow-lg shadow-emerald-500/20 disabled:opacity-50 disabled:cursor-not-allowed transition-all active:scale-[0.98]"
              >
                Review Transaction
                <ArrowUpRight className="w-4 h-4" />
              </button>
            </form>
          </>
        )}
      </div>

      {/* Confirmation Modal */}
      <ConfirmationModal
        isOpen={isModalOpen}
        onClose={() => setIsModalOpen(false)}
        onConfirm={handleConfirmSend}
        recipient={cleanRecipient}
        amount={numAmount}
        fee={numFee}
        availableBalance={availableBalance}
        isSubmitting={isSubmitting}
      />
    </div>
  );
};
