import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { BrowserRouter } from "react-router-dom";
import { describe, expect, it, vi } from "vitest";
import { LoginPage } from "../LoginPage";
import { AuthContext, AuthContextType } from "../../auth/AuthContext";
import { ApiClientError } from "../../api/client";

const createMockAuthContext = (overrides?: Partial<AuthContextType>): AuthContextType => ({
  user: null,
  wallet: null,
  isLoading: false,
  isAuthenticated: false,
  login: vi.fn(),
  register: vi.fn(),
  logout: vi.fn(),
  refreshAuth: vi.fn(),
  ...overrides,
});

describe("LoginPage", () => {
  it("renders username/email and password inputs and submit button", () => {
    const mockAuth = createMockAuthContext();
    render(
      <AuthContext.Provider value={mockAuth}>
        <BrowserRouter>
          <LoginPage />
        </BrowserRouter>
      </AuthContext.Provider>
    );

    expect(screen.getByLabelText(/username or email/i)).toBeInTheDocument();
    expect(screen.getByLabelText(/password/i)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /sign in/i })).toBeInTheDocument();
  });

  it("validates empty input and shows error when submitting form directly", async () => {
    const mockAuth = createMockAuthContext();
    const { container } = render(
      <AuthContext.Provider value={mockAuth}>
        <BrowserRouter>
          <LoginPage />
        </BrowserRouter>
      </AuthContext.Provider>
    );

    const form = container.querySelector("form")!;
    fireEvent.submit(form);

    await waitFor(() => {
      expect(screen.getByText(/please enter your username or email/i)).toBeInTheDocument();
    });
  });

  it("displays error message from backend when login fails", async () => {
    const mockAuth = createMockAuthContext({
      login: vi.fn().mockRejectedValue(new ApiClientError(401, "INVALID_CREDENTIALS", "Invalid username or password")),
    });

    render(
      <AuthContext.Provider value={mockAuth}>
        <BrowserRouter>
          <LoginPage />
        </BrowserRouter>
      </AuthContext.Provider>
    );

    const identifierInput = screen.getByLabelText(/username or email/i);
    const passwordInput = screen.getByLabelText(/password/i);

    fireEvent.change(identifierInput, { target: { value: "alice" } });
    fireEvent.change(passwordInput, { target: { value: "wrongpassword123" } });

    const submitBtn = screen.getByRole("button", { name: /sign in/i });
    fireEvent.click(submitBtn);

    await waitFor(() => {
      expect(screen.getByText(/invalid username or password/i)).toBeInTheDocument();
    });
  });
});
