import React from "react";
import { BrowserRouter, Navigate, Route, Routes } from "react-router-dom";
import { AuthProvider } from "./auth/AuthProvider";
import { ProtectedRoute } from "./auth/ProtectedRoute";
import { AppShell } from "./components/AppShell";
import { LoginPage } from "./pages/LoginPage";
import { RegisterPage } from "./pages/RegisterPage";
import { DashboardPage } from "./pages/DashboardPage";
import { SendPage } from "./pages/SendPage";
import { ReceivePage } from "./pages/ReceivePage";
import { MiningPage } from "./pages/MiningPage";
import { ExplorerHomePage } from "./pages/ExplorerHomePage";
import { BlockDetailPage } from "./pages/BlockDetailPage";
import { TransactionDetailPage } from "./pages/TransactionDetailPage";
import { AddressDetailPage } from "./pages/AddressDetailPage";
import { MempoolPage } from "./pages/MempoolPage";

export const App: React.FC = () => {
  return (
    <BrowserRouter>
      <AuthProvider>
        <Routes>
          {/* Public Authentication Routes */}
          <Route path="/login" element={<LoginPage />} />
          <Route path="/register" element={<RegisterPage />} />

          {/* Protected Wallet & Explorer Application Routes */}
          <Route element={<ProtectedRoute />}>
            <Route element={<AppShell />}>
              <Route path="/app" element={<DashboardPage />} />
              <Route path="/app/mining" element={<MiningPage />} />
              <Route path="/app/send" element={<SendPage />} />
              <Route path="/app/receive" element={<ReceivePage />} />

              {/* Explorer Routes (Phase 14 - Requires Login) */}
              <Route path="/explorer" element={<ExplorerHomePage />} />
              <Route path="/explorer/block/:id" element={<BlockDetailPage />} />
              <Route path="/explorer/tx/:txid" element={<TransactionDetailPage />} />
              <Route path="/explorer/address/:address" element={<AddressDetailPage />} />
              <Route path="/explorer/mempool" element={<MempoolPage />} />
            </Route>
          </Route>

          {/* Fallback Redirect */}
          <Route path="*" element={<Navigate to="/app" replace />} />
        </Routes>
      </AuthProvider>
    </BrowserRouter>
  );
};

export default App;
