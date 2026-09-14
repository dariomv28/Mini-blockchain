import { render, screen } from "@testing-library/react";
import { BrowserRouter } from "react-router-dom";
import { describe, expect, it } from "vitest";
import { BalanceCard } from "../BalanceCard";
import { WalletSummary } from "../../types/api";

const mockSummary: WalletSummary = {
  address: "PYC_test123456",
  public_key: "02abcd",
  confirmed_balance: 50,
  available_balance: 40,
  pending_outgoing: 10,
  pending_incoming: 5,
  pending_count: 2,
};

describe("BalanceCard", () => {
  it("renders balances accurately when loaded", () => {
    render(
      <BrowserRouter>
        <BalanceCard summary={mockSummary} isLoading={false} />
      </BrowserRouter>
    );

    expect(screen.getByText("50")).toBeInTheDocument();
    expect(screen.getByText("40 PYC")).toBeInTheDocument();
    expect(screen.getByText("-10 PYC")).toBeInTheDocument();
    expect(screen.getByText("+5 PYC")).toBeInTheDocument();
  });

  it("renders send and receive action links", () => {
    render(
      <BrowserRouter>
        <BalanceCard summary={mockSummary} isLoading={false} />
      </BrowserRouter>
    );

    const sendBtn = screen.getByRole("link", { name: /send pyc/i });
    const receiveBtn = screen.getByRole("link", { name: /receive/i });

    expect(sendBtn).toHaveAttribute("href", "/app/send");
    expect(receiveBtn).toHaveAttribute("href", "/app/receive");
  });

  it("renders error state with retry button instead of 0 PYC when isError is true", () => {
    render(
      <BrowserRouter>
        <BalanceCard
          summary={null}
          isLoading={false}
          isError={true}
          error={new Error("Failed to fetch balance from node")}
        />
      </BrowserRouter>
    );

    expect(screen.getByText(/failed to load balance/i)).toBeInTheDocument();
    expect(screen.getByText(/failed to fetch balance from node/i)).toBeInTheDocument();
    expect(screen.queryByText("0 PYC")).not.toBeInTheDocument();
  });
});
