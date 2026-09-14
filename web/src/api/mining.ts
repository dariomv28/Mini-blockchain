import { apiFetch } from "./client";
import {
  CandidateTemplate,
  MempoolTransaction,
  MiningCancelResponse,
  MiningJob,
  MiningJobStartResponse,
} from "../types/mining";

export async function previewMiningTemplate(
  maxTransactions: number = 100,
  maxBytes: number = 100000
): Promise<CandidateTemplate> {
  return apiFetch<CandidateTemplate>("/api/v1/mining/template", {
    method: "POST",
    body: JSON.stringify({
      max_transactions: maxTransactions,
      max_bytes: maxBytes,
    }),
  });
}

export async function startMiningJob(options?: {
  max_transactions?: number;
  max_bytes?: number;
  max_nonce?: number;
}): Promise<MiningJobStartResponse> {
  return apiFetch<MiningJobStartResponse>("/api/v1/mining/jobs", {
    method: "POST",
    body: JSON.stringify(options || {}),
  });
}

export async function getActiveMiningJob(): Promise<MiningJob | null> {
  return apiFetch<MiningJob | null>("/api/v1/mining/jobs/active", {
    method: "GET",
  });
}

export async function getMiningJob(jobId: string): Promise<MiningJob> {
  return apiFetch<MiningJob>(`/api/v1/mining/jobs/${encodeURIComponent(jobId)}`, {
    method: "GET",
  });
}

export async function cancelMiningJob(jobId: string): Promise<MiningCancelResponse> {
  return apiFetch<MiningCancelResponse>(`/api/v1/mining/jobs/${encodeURIComponent(jobId)}`, {
    method: "DELETE",
  });
}

export async function getMempoolTransactions(): Promise<MempoolTransaction[]> {
  const res = await apiFetch<{ count: number; total_bytes: number; transactions: MempoolTransaction[] } | MempoolTransaction[]>("/api/v1/mempool", {
    method: "GET",
  });
  if (Array.isArray(res)) {
    return res;
  }
  if (res && Array.isArray(res.transactions)) {
    return res.transactions;
  }
  return [];
}
