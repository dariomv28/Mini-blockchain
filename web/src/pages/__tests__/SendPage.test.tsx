import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { BrowserRouter } from "react-router-dom";
import { describe, expect, it, vi } from "vitest";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { SendPage } from "../SendPage";
import * as walletApi from "../../api/wallet";
import { AuthContext, AuthContextType } from "../../auth/AuthContext";

vi.mock("../../api/wallet", () => ({
  getWalletSummary: vi.fn().mockResolvedValue({
    address: "PYC_sender_address",
    public_key: "02abcdef123456",
    confirmed_balance: 50,
    available_balance: 50,
    pending_outgoing: 0,
    pending_incoming: 0,
    pending_count: 0,
  }),
  sendTransaction: vi.fn().mockResolvedValue({
    txid: "tx_abc123def456",
    status: "pending",
  }),
}));

const mockAuth: AuthContextType = {
  user: { id: 1, username: "alice", email: "alice@example.com" },
  wallet: { address: "PYC_sender_address", public_key: "02abcdef123456" },
  isLoading: false,
  isAuthenticated: true,
  login: vi.fn(),
  register: vi.fn(),
  logout: vi.fn(),
  refreshAuth: vi.fn(),
};

const createTestQueryClient = () =>
  new QueryClient({
    defaultOptions: {
      queries: {
        retry: false,
      },
    },
  });

const renderSendPage = (queryClient = createTestQueryClient()) => {
  return render(
    <AuthContext.Provider value={mockAuth}>
      <QueryClientProvider client={queryClient}>
        <BrowserRouter>
          <SendPage />
        </BrowserRouter>
      </QueryClientProvider>
    </AuthContext.Provider>
  );
};

describe("SendPage", () => {
  it("renders recipient, amount, and fee inputs", async () => {
    renderSendPage();

    expect(screen.getByLabelText(/recipient pychain address/i)).toBeInTheDocument();
    expect(screen.getByLabelText(/amount \(pyc\)/i)).toBeInTheDocument();
    expect(screen.getByLabelText(/miner fee \(pyc\)/i)).toBeInTheDocument();

    await waitFor(() => {
      expect(screen.getByText(/available:/i)).toBeInTheDocument();
    });
  });

  it("validates invalid recipient address format", async () => {
    renderSendPage();

    await waitFor(() => {
      expect(screen.getByText("50 PYC")).toBeInTheDocument();
    });

    const recipientInput = screen.getByLabelText(/recipient pychain address/i);
    const amountInput = screen.getByLabelText(/amount \(pyc\)/i);
    const submitBtn = screen.getByRole("button", { name: /review transaction/i });

    fireEvent.change(recipientInput, { target: { value: "invalid_address_123" } });
    fireEvent.change(amountInput, { target: { value: "10" } });
    fireEvent.click(submitBtn);

    await waitFor(() => {
      expect(
        screen.getByText(/recipient address must begin with 'PYC_'/i)
      ).toBeInTheDocument();
    });
  });

  it("rejects exponential notation in amount and fee inputs", async () => {
    renderSendPage();

    await waitFor(() => {
      expect(screen.getByText("50 PYC")).toBeInTheDocument();
    });

    const recipientInput = screen.getByLabelText(/recipient pychain address/i);
    const amountInput = screen.getByLabelText(/amount \(pyc\)/i);
    const submitBtn = screen.getByRole("button", { name: /review transaction/i });

    fireEvent.change(recipientInput, { target: { value: "PYC_valid_recipient_123" } });
    fireEvent.change(amountInput, { target: { value: "1e2" } });
    fireEvent.click(submitBtn);

    await waitFor(() => {
      expect(
        screen.getByText(/exponential notation and decimals are not allowed/i)
      ).toBeInTheDocument();
    });
  });

  it("opens confirmation modal when valid inputs are provided and reuses idempotency key on retry", async () => {
    const sendMock = vi.mocked(walletApi.sendTransaction);
    sendMock.mockClear();
    sendMock.mockRejectedValueOnce(new Error("Network timeout"));
    sendMock.mockResolvedValueOnce({ txid: "tx_retry_success", status: "pending" });

    renderSendPage();

    await waitFor(() => {
      expect(screen.getByText("50 PYC")).toBeInTheDocument();
    });

    const recipientInput = screen.getByLabelText(/recipient pychain address/i);
    const amountInput = screen.getByLabelText(/amount \(pyc\)/i);
    const reviewBtn = screen.getByRole("button", { name: /review transaction/i });

    fireEvent.change(recipientInput, { target: { value: "PYC_valid_recipient_999" } });
    fireEvent.change(amountInput, { target: { value: "15" } });
    fireEvent.click(reviewBtn);

    await waitFor(() => {
      expect(screen.getByText(/confirm transaction/i)).toBeInTheDocument();
    });

    const sendNowBtn1 = screen.getByRole("button", { name: /send now/i });
    fireEvent.click(sendNowBtn1);

    await waitFor(() => {
      expect(screen.getByText(/network communication error/i)).toBeInTheDocument();
    });

    expect(sendMock).toHaveBeenCalledTimes(1);
    const firstKey = sendMock.mock.calls[0][1];
    expect(firstKey).toBeTruthy();

    // User retries without changing form inputs
    fireEvent.click(screen.getByRole("button", { name: /review transaction/i }));
    await waitFor(() => {
      expect(screen.getByText(/confirm transaction/i)).toBeInTheDocument();
    });
    fireEvent.click(screen.getByRole("button", { name: /send now/i }));

    await waitFor(() => {
      expect(screen.getByText(/transaction broadcasted/i)).toBeInTheDocument();
    });

    expect(sendMock).toHaveBeenCalledTimes(2);
    const secondKey = sendMock.mock.calls[1][1];
    expect(secondKey).toBe(firstKey);
  });
});
