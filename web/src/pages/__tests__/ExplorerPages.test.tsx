import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { describe, expect, it, vi } from "vitest";
import { ExplorerHomePage } from "../ExplorerHomePage";
import { BlockDetailPage } from "../BlockDetailPage";
import { TransactionDetailPage } from "../TransactionDetailPage";
import { AddressDetailPage } from "../AddressDetailPage";
import { MempoolPage } from "../MempoolPage";

vi.mock("../../api/explorer", () => ({
  getExplorerStats: vi.fn().mockResolvedValue({
    height: 12,
    tip_hash: "0000abc123def456789012345678901234567890123456789012345678901234",
    mempool_count: 2,
    peer_count: 3,
    total_confirmed_transactions: 25,
  }),
  getLatestBlocks: vi.fn().mockResolvedValue({
    total_blocks: 13,
    blocks: [
      {
        height: 12,
        hash: "0000abc123def456789012345678901234567890123456789012345678901234",
        previous_block_hash: "0000prev123def456789012345678901234567890123456789012345678901234",
        timestamp: 1789450000,
        transaction_count: 2,
        size_bytes: 450,
        miner_address: "PYC_miner_test_address_12345",
        difficulty: 16,
        nonce: 4210,
      },
    ],
    limit: 10,
    offset: 0,
  }),
  getBlockByHeight: vi.fn().mockResolvedValue({
    height: 12,
    hash: "0000abc123def456789012345678901234567890123456789012345678901234",
    version: 1,
    previous_block_hash: "0000prev123def456789012345678901234567890123456789012345678901234",
    merkle_root: "merkle_root_test_hash_1234567890123456789012345678901234567890",
    timestamp: 1789450000,
    difficulty: 16,
    nonce: 4210,
    transaction_count: 1,
    size_bytes: 450,
    miner_address: "PYC_miner_test_address_12345",
    total_fees: 2,
    total_output_amount: 52,
    transactions: [
      {
        txid: "coinbase_txid_123456789012345678901234567890123456789012345678901234",
        status: "confirmed",
        block_height: 12,
        block_hash: "0000abc123def456789012345678901234567890123456789012345678901234",
        timestamp: 1789450000,
        version: 1,
        is_coinbase: true,
        inputs: [],
        outputs: [
          {
            index: 0,
            recipient_address: "PYC_miner_test_address_12345",
            amount: 52,
          },
        ],
        fee: 0,
        size_bytes: 200,
      },
    ],
  }),
  getBlockByHash: vi.fn(),
  getTransaction: vi.fn().mockResolvedValue({
    txid: "txid_test_123456789012345678901234567890123456789012345678901234567890",
    status: "confirmed",
    block_height: 12,
    block_hash: "0000abc123def456789012345678901234567890123456789012345678901234",
    timestamp: 1789450000,
    version: 1,
    is_coinbase: false,
    inputs: [
      {
        previous_tx_id: "prev_tx_hash_12345678901234567890123456789012345678901234567890",
        output_index: 0,
        public_key: "pubkey_hex_12345",
        signature: "sig_hex_12345",
        source_address: "PYC_alice_test_address_12345",
        amount: 50,
      },
    ],
    outputs: [
      {
        index: 0,
        recipient_address: "PYC_bob_test_address_12345",
        amount: 15,
      },
      {
        index: 1,
        recipient_address: "PYC_alice_test_address_12345",
        amount: 34,
      },
    ],
    fee: 1,
    size_bytes: 250,
  }),
  getAddressDetail: vi.fn().mockResolvedValue({
    address: "PYC_alice_test_address_12345",
    confirmed_balance: 84,
    utxo_count: 2,
    utxos: [
      {
        txid: "tx_utxo_12345678901234567890123456789012345678901234567890",
        output_index: 0,
        amount: 50,
        recipient_address: "PYC_alice_test_address_12345",
      },
    ],
    total_transactions: 1,
    transactions: [
      {
        txid: "tx_hist_12345678901234567890123456789012345678901234567890",
        block_height: 12,
        timestamp: 1789450000,
        status: "confirmed",
        direction: "mined",
        amount: 50,
        fee: 0,
      },
    ],
    limit: 15,
    offset: 0,
  }),
  getMempool: vi.fn().mockResolvedValue({
    count: 1,
    total_bytes: 250,
    transactions: [
      {
        txid: "pending_tx_12345678901234567890123456789012345678901234567890",
        timestamp: 1789450500,
        inputs_count: 1,
        outputs_count: 2,
        fee: 2,
        size_bytes: 250,
        status: "pending",
      },
    ],
  }),
  searchExplorer: vi.fn().mockResolvedValue({
    query: "12",
    result_type: "block",
    target_url: "/explorer/block/12",
    payload: { height: 12 },
  }),
}));

describe("Explorer Pages", () => {
  it("renders ExplorerHomePage with stats and blocks correctly", async () => {
    render(
      <MemoryRouter initialEntries={["/explorer"]}>
        <ExplorerHomePage />
      </MemoryRouter>
    );

    expect(screen.getByText("Explore the PyChain Blockchain")).toBeInTheDocument();

    await waitFor(() => {
      expect(screen.getAllByText("#12")[0]).toBeInTheDocument();
      expect(screen.getByText("Latest Blocks")).toBeInTheDocument();
      expect(screen.getByText("Mempool Queue")).toBeInTheDocument();
    });
  });

  it("renders BlockDetailPage correctly", async () => {
    render(
      <MemoryRouter initialEntries={["/explorer/block/12"]}>
        <Routes>
          <Route path="/explorer/block/:id" element={<BlockDetailPage />} />
        </Routes>
      </MemoryRouter>
    );

    await waitFor(() => {
      expect(screen.getByRole("heading", { level: 1 })).toHaveTextContent(/Block #12/);
      expect(screen.getByText("Included Transactions")).toBeInTheDocument();
    });
  });

  it("renders TransactionDetailPage with inputs and outputs correctly", async () => {
    render(
      <MemoryRouter initialEntries={["/explorer/tx/txid_test_123"]}>
        <Routes>
          <Route path="/explorer/tx/:txid" element={<TransactionDetailPage />} />
        </Routes>
      </MemoryRouter>
    );

    await waitFor(() => {
      expect(screen.getByText("Transaction Overview")).toBeInTheDocument();
      expect(screen.getByText("Confirmed")).toBeInTheDocument();
      expect(screen.getByText("Inputs (1)")).toBeInTheDocument();
      expect(screen.getByText("Outputs (2)")).toBeInTheDocument();
    });
  });

  it("renders AddressDetailPage with balance and tabs correctly", async () => {
    render(
      <MemoryRouter initialEntries={["/explorer/address/PYC_alice_test_address_12345"]}>
        <Routes>
          <Route path="/explorer/address/:address" element={<AddressDetailPage />} />
        </Routes>
      </MemoryRouter>
    );

    await waitFor(() => {
      expect(screen.getByText("84 PYC")).toBeInTheDocument();
      expect(screen.getByText("Transaction History (1)")).toBeInTheDocument();
    });

    // Switch to UTXOs tab
    fireEvent.click(screen.getByText("Unspent Outputs (2)"));

    await waitFor(() => {
      expect(screen.getByText("+50 PYC")).toBeInTheDocument();
    });
  });

  it("renders MempoolPage with pending transactions correctly", async () => {
    render(
      <MemoryRouter initialEntries={["/explorer/mempool"]}>
        <MempoolPage />
      </MemoryRouter>
    );

    await waitFor(() => {
      expect(screen.getByText("Live Memory Pool")).toBeInTheDocument();
      expect(screen.getByText("+2 PYC")).toBeInTheDocument();
    });
  });
});
