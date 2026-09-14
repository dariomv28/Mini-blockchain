import { apiFetch } from "./client";
import { SendReceipt, SendRequest, TransactionItem, WalletSummary } from "../types/api";

export async function getWalletSummary(): Promise<WalletSummary> {
  return apiFetch<WalletSummary>("/api/v1/wallet", {
    method: "GET",
  });
}

export async function getTransactionHistory(start = 0, limit = 20): Promise<TransactionItem[]> {
  return apiFetch<TransactionItem[]>(`/api/v1/wallet/transactions?start=${start}&limit=${limit}`, {
    method: "GET",
  });
}

export async function sendTransaction(params: SendRequest, idempotencyKey: string): Promise<SendReceipt> {
  return apiFetch<SendReceipt>("/api/v1/wallet/send", {
    method: "POST",
    body: JSON.stringify(params),
    idempotencyKey,
  });
}
