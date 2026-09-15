import { apiFetch } from "./client";
import {
  EnrichedTransaction,
  ExplorerAddressDetail,
  ExplorerBlockDetail,
  ExplorerBlocksResponse,
  ExplorerMempoolResponse,
  ExplorerSearchResponse,
  ExplorerStats,
} from "../types/explorer";

export async function getExplorerStats(): Promise<ExplorerStats> {
  return apiFetch<ExplorerStats>("/api/v1/explorer/stats");
}

export async function getLatestBlocks(
  limit: number = 10,
  offset: number = 0
): Promise<ExplorerBlocksResponse> {
  return apiFetch<ExplorerBlocksResponse>(
    `/api/v1/explorer/blocks?limit=${limit}&offset=${offset}`
  );
}

export async function getBlockByHeight(height: number): Promise<ExplorerBlockDetail> {
  return apiFetch<ExplorerBlockDetail>(`/api/v1/explorer/blocks/height/${height}`);
}

export async function getBlockByHash(hash: string): Promise<ExplorerBlockDetail> {
  return apiFetch<ExplorerBlockDetail>(`/api/v1/explorer/blocks/hash/${encodeURIComponent(hash)}`);
}

export async function getTransaction(txid: string): Promise<EnrichedTransaction> {
  return apiFetch<EnrichedTransaction>(`/api/v1/explorer/transactions/${encodeURIComponent(txid)}`);
}

export async function getAddressDetail(
  address: string,
  limit: number = 20,
  offset: number = 0
): Promise<ExplorerAddressDetail> {
  return apiFetch<ExplorerAddressDetail>(
    `/api/v1/explorer/addresses/${encodeURIComponent(address)}?limit=${limit}&offset=${offset}`
  );
}

export async function getMempool(): Promise<ExplorerMempoolResponse> {
  return apiFetch<ExplorerMempoolResponse>("/api/v1/explorer/mempool");
}

export async function searchExplorer(query: string): Promise<ExplorerSearchResponse> {
  return apiFetch<ExplorerSearchResponse>(
    `/api/v1/explorer/search?q=${encodeURIComponent(query.trim())}`
  );
}
