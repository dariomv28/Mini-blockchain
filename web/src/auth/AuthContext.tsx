import { createContext, useContext } from "react";
import { IdentityResponse, User, WalletInfo } from "../types/api";

export interface AuthContextType {
  user: User | null;
  wallet: WalletInfo | null;
  isLoading: boolean;
  isAuthenticated: boolean;
  login: (identifier: string, password: string) => Promise<IdentityResponse>;
  register: (username: string, email: string, password: string) => Promise<IdentityResponse>;
  logout: () => Promise<void>;
  refreshAuth: () => Promise<void>;
}

export const AuthContext = createContext<AuthContextType | null>(null);

export function useAuth(): AuthContextType {
  const context = useContext(AuthContext);
  if (!context) {
    throw new Error("useAuth must be used within an AuthProvider");
  }
  return context;
}
