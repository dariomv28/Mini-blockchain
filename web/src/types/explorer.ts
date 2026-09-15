export interface ExplorerStats {
  height: number;
  tip_hash: string;
  mempool_count: number;
  peer_count: number;
  total_confirmed_transactions: number;
}

export interface ExplorerBlockListItem {
  height: number;
  hash: string;
  previous_block_hash: string;
  timestamp: number;
  transaction_count: number;
  size_bytes: number;
  miner_address: string | null;
  difficulty: number;
  nonce: number;
}

export interface ExplorerBlocksResponse {
  total_blocks: number;
  blocks: ExplorerBlockListItem[];
  limit: number;
  offset: number;
}

export interface EnrichedTxInput {
  previous_tx_id: string;
  output_index: number;
  public_key: string;
  signature: string;
  source_address?: string | null;
  amount?: number | null;
}

export interface EnrichedTxOutput {
  index: number;
  recipient_address: string;
  amount: number;
}

export interface EnrichedTransaction {
  txid: string;
  status: "pending" | "confirmed";
  block_height?: number | null;
  block_hash?: string | null;
  timestamp: number;
  version: number;
  is_coinbase: boolean;
  inputs: EnrichedTxInput[];
  outputs: EnrichedTxOutput[];
  fee: number;
  size_bytes: number;
}

export interface ExplorerBlockDetail {
  height: number;
  hash: string;
  version: number;
  previous_block_hash: string;
  merkle_root: string;
  timestamp: number;
  difficulty: number;
  nonce: number;
  transaction_count: number;
  size_bytes: number;
  miner_address?: string | null;
  total_fees: number;
  total_output_amount: number;
  transactions: EnrichedTransaction[];
}

export interface ExplorerAddressHistoryItem {
  txid: string;
  block_height: number | null;
  timestamp: number;
  status: "pending" | "confirmed";
  direction: "sent" | "received" | "mined";
  amount: number;
  fee: number;
}

export interface ExplorerUTXOItem {
  txid: string;
  output_index: number;
  amount: number;
  recipient_address: string;
}

export interface ExplorerAddressDetail {
  address: string;
  confirmed_balance: number;
  utxo_count: number;
  utxos: ExplorerUTXOItem[];
  total_transactions: number;
  transactions: ExplorerAddressHistoryItem[];
  limit: number;
  offset: number;
}

export interface ExplorerMempoolEntry {
  txid: string;
  timestamp: number;
  inputs_count: number;
  outputs_count: number;
  fee: number;
  size_bytes: number;
  status: string;
}

export interface ExplorerMempoolResponse {
  count: number;
  total_bytes: number;
  transactions: ExplorerMempoolEntry[];
}

export interface ExplorerSearchResponse {
  query: string;
  result_type: "block" | "transaction" | "address" | "not_found";
  target_url?: string | null;
  payload?: Record<string, any> | null;
}
