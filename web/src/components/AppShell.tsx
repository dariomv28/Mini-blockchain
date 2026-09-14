import React from "react";
import { Outlet } from "react-router-dom";
import { Navbar } from "./Navbar";

export const AppShell: React.FC = () => {
  return (
    <div className="min-h-screen flex flex-col bg-[#080c14] text-slate-100">
      <Navbar />
      <main className="flex-1 max-w-7xl w-full mx-auto px-4 sm:px-6 lg:px-8 py-8">
        <Outlet />
      </main>
      <footer className="border-t border-slate-800/80 py-6 text-center text-xs text-slate-500">
        <p>PyChain — Educational Bitcoin-like Blockchain Platform • Phase 12 Web Wallet</p>
      </footer>
    </div>
  );
};
