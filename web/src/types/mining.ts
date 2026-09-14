export type MiningJobStatus =
  | "QUEUED"
  | "MINING"
  | "FOUND"
  | "ACCEPTED"
  | "STALE"
  | "FAILED"
  | "CANCELLED";

export interface CandidateTemplate {
  previous_block_hash: string;
  merkle_root: string;
  difficulty: number;
  nonce: number;
  template_height: number;
  timestamp: number;
  miner_address: string;
  transactions: any[];
  transaction_count: number;
  subsidy: number;
  fees: number;
  total_reward: number;
}

export interface MiningJob {
  id: string;
  status: MiningJobStatus;
  miner_address: string;
  created_at: number;
  started_at?: number | null;
  finished_at?: number | null;
  template_height: number;
  previous_hash: string;
  transaction_count: number;
  difficulty: number;
  result_hash?: string | null;
  nonce?: number | null;
  hashes_tried: number;
  current_hash?: string | null;
  elapsed_seconds: number;
  accepted?: boolean | null;
  error?: string | null;
  subsidy: number;
  fees: number;
  total_reward: number;
}

export interface MiningJobStartResponse {
  job_id: string;
  status: string;
}

export interface MiningCancelResponse {
  job_id: string;
  cancelled: boolean;
}

export interface MempoolTransaction {
  txid: string;
  timestamp: number;
  inputs: any[];
  outputs: Array<{
    amount: number;
    recipient_address: string;
  }>;
  fee?: number;
}
