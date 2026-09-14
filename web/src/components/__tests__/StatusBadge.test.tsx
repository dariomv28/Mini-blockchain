import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { DirectionBadge, StatusBadge } from "../StatusBadge";

describe("StatusBadge", () => {
  it("renders pending badge with pulsing amber style", () => {
    render(<StatusBadge status="pending" />);
    const badge = screen.getByText("Pending");
    expect(badge).toBeInTheDocument();
  });

  it("renders confirmed badge with emerald style", () => {
    render(<StatusBadge status="confirmed" />);
    const badge = screen.getByText("Confirmed");
    expect(badge).toBeInTheDocument();
  });
});

describe("DirectionBadge", () => {
  it("renders sent badge", () => {
    render(<DirectionBadge direction="sent" />);
    expect(screen.getByText("Sent")).toBeInTheDocument();
  });

  it("renders received badge", () => {
    render(<DirectionBadge direction="received" />);
    expect(screen.getByText("Received")).toBeInTheDocument();
  });
});
