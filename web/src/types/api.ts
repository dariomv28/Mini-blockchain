export interface User {
  id: number;
  username: string;
  email: string;
}

export interface WalletInfo {
  address: string;
  public_key?: string;
}

export interface IdentityResponse {
  user: User;
  wallet: WalletInfo;
  csrf_token?: string;
}

export interface WalletSummary {
  address: string;
  public_key: string;
  confirmed_balance: number;
  available_balance: number;
  pending_outgoing: number;
  pending_incoming: number;
  pending_count: number;
}

export interface TransactionItem {
  txid: string;
  status: "pending" | "confirmed";
  direction: "sent" | "received";
  amount: number;
  timestamp: number;
  block_height: number | null;
}

export interface SendRequest {
  recipient_address: string;
  amount: number;
  fee: number;
}

export interface SendReceipt {
  txid: string;
  status: "pending";
}

export interface ApiErrorPayload {
  error?: {
    code?: string;
    message?: string;
  };
  detail?: {
    error?: string;
    message?: string;
  } | string;
}

export interface NodeStatus {
  node_id?: string;
  state?: string;
  height?: number;
  tip_hash?: string;
  pending_count?: number;
  peer_count?: number;
}
