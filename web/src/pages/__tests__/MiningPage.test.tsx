import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { BrowserRouter } from "react-router-dom";
import { describe, expect, it, vi } from "vitest";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MiningPage } from "../MiningPage";
import * as miningApi from "../../api/mining";

vi.mock("../../api/mining", () => ({
  previewMiningTemplate: vi.fn().mockResolvedValue({
    previous_block_hash: "0000abc123def4567890",
    merkle_root: "merkle_root_test_hash_12345",
    difficulty: 16,
    nonce: 0,
    template_height: 5,
    timestamp: 1789400000,
    miner_address: "PYC_miner_test_address_12345",
    transactions: [],
    transaction_count: 1,
    subsidy: 50,
    fees: 0,
    total_reward: 50,
  }),
  getMempoolTransactions: vi.fn().mockResolvedValue([]),
  getActiveMiningJob: vi.fn().mockResolvedValue(null),
  startMiningJob: vi.fn().mockResolvedValue({
    job_id: "test-job-uuid-1234",
    status: "QUEUED",
  }),
  cancelMiningJob: vi.fn().mockResolvedValue({
    job_id: "test-job-uuid-1234",
    cancelled: true,
  }),
  getMiningJob: vi.fn(),
}));

const createTestQueryClient = () =>
  new QueryClient({
    defaultOptions: {
      queries: {
        retry: false,
      },
    },
  });

const renderMiningPage = (queryClient = createTestQueryClient()) => {
  return render(
    <QueryClientProvider client={queryClient}>
      <BrowserRouter>
        <MiningPage />
      </BrowserRouter>
    </QueryClientProvider>
  );
};

describe("MiningPage", () => {
  it("renders candidate template and mempool table correctly", async () => {
    renderMiningPage();

    expect(screen.getByText("Mining Dashboard")).toBeInTheDocument();
    expect(screen.getByText("Candidate Block")).toBeInTheDocument();
    expect(screen.getByText("Memory Pool (Mempool)")).toBeInTheDocument();

    await waitFor(() => {
      expect(screen.getByText("Height #5")).toBeInTheDocument();
      expect(screen.getByText("+50 PYC")).toBeInTheDocument();
      expect(screen.getByText("Mempool is currently empty")).toBeInTheDocument();
    });
  });

  it("starts mining when Mine This Block is clicked", async () => {
    renderMiningPage();

    await waitFor(() => {
      expect(screen.getByText("Mine This Block")).toBeInTheDocument();
    });

    const mineBtn = screen.getByText("Mine This Block");
    fireEvent.click(mineBtn);

    await waitFor(() => {
      expect(miningApi.startMiningJob).toHaveBeenCalled();
      expect(screen.getByText("Proof-of-Work Mining in Progress")).toBeInTheDocument();
      expect(screen.getByText("Cancel Mining")).toBeInTheDocument();
    });
  });

  it("cancels mining when Cancel Mining is clicked", async () => {
    renderMiningPage();

    await waitFor(() => {
      expect(screen.getByText("Mine This Block")).toBeInTheDocument();
    });

    fireEvent.click(screen.getByText("Mine This Block"));

    await waitFor(() => {
      expect(screen.getByText("Cancel Mining")).toBeInTheDocument();
    });

    fireEvent.click(screen.getByText("Cancel Mining"));

    await waitFor(() => {
      expect(miningApi.cancelMiningJob).toHaveBeenCalledWith("test-job-uuid-1234");
      expect(screen.getByText("Mining Cancelled")).toBeInTheDocument();
    });
  });
});
