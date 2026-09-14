import React, { useCallback, useEffect, useState } from "react";
import { useQueryClient } from "@tanstack/react-query";
import { AuthContext } from "./AuthContext";
import * as authApi from "../api/auth";
import { onUnauthorized } from "../api/client";
import { IdentityResponse, User, WalletInfo } from "../types/api";

export const AuthProvider: React.FC<{ children: React.ReactNode }> = ({ children }) => {
  const queryClient = useQueryClient();
  const [user, setUser] = useState<User | null>(null);
  const [wallet, setWallet] = useState<WalletInfo | null>(null);
  const [isLoading, setIsLoading] = useState<boolean>(true);

  const clearSession = useCallback(() => {
    setUser(null);
    setWallet(null);
    queryClient.clear();
  }, [queryClient]);

  const checkAuth = useCallback(async () => {
    try {
      const data = await authApi.getMe();
      setUser(data.user);
      setWallet(data.wallet);
    } catch {
      clearSession();
    } finally {
      setIsLoading(false);
    }
  }, [clearSession]);

  useEffect(() => {
    checkAuth();
    const unsubscribe = onUnauthorized(() => {
      clearSession();
    });
    return unsubscribe;
  }, [checkAuth, clearSession]);

  const handleLogin = async (identifier: string, password: string): Promise<IdentityResponse> => {
    queryClient.clear();
    const res = await authApi.login(identifier, password);
    setUser(res.user);
    setWallet(res.wallet);
    return res;
  };

  const handleRegister = async (username: string, email: string, password: string): Promise<IdentityResponse> => {
    return authApi.register(username, email, password);
  };

  const handleLogout = async () => {
    await authApi.logout();
    clearSession();
  };

  return (
    <AuthContext.Provider
      value={{
        user,
        wallet,
        isLoading,
        isAuthenticated: !!user,
        login: handleLogin,
        register: handleRegister,
        logout: handleLogout,
        refreshAuth: checkAuth,
      }}
    >
      {children}
    </AuthContext.Provider>
  );
};
