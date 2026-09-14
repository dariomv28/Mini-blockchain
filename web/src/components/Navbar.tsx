import React from "react";
import { Link, useLocation } from "react-router-dom";
import { useAuth } from "../auth/AuthContext";
import { useWebSocket } from "../hooks/useWebSocket";
import { ArrowDownLeft, ArrowUpRight, Cpu, Globe, LayoutDashboard, LogOut, Radio, User as UserIcon } from "lucide-react";

export const Navbar: React.FC = () => {
  const { user, logout } = useAuth();
  const location = useLocation();
  const { isConnected, nodeStatus } = useWebSocket();

  const navItems = [
    { name: "Dashboard", path: "/app", icon: LayoutDashboard },
    { name: "Send", path: "/app/send", icon: ArrowUpRight },
    { name: "Receive", path: "/app/receive", icon: ArrowDownLeft },
  ];

  return (
    <header className="sticky top-0 z-40 w-full border-b border-slate-800 bg-[#080c14]/80 backdrop-blur-xl">
      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 h-16 flex items-center justify-between">
        {/* Left: Brand logo */}
        <div className="flex items-center gap-6">
          <Link to="/app" className="flex items-center gap-2.5 group">
            <div className="w-9 h-9 rounded-xl bg-gradient-to-tr from-emerald-500 to-cyan-500 flex items-center justify-center shadow-md shadow-emerald-500/20 group-hover:scale-105 transition-transform">
              <Cpu className="w-5 h-5 text-slate-950 stroke-[2.5]" />
            </div>
            <div className="flex flex-col">
              <span className="font-extrabold text-lg tracking-tight text-white flex items-center gap-1">
                PyChain
                <span className="text-[10px] uppercase font-bold tracking-wider px-1.5 py-0.5 rounded bg-emerald-500/10 text-emerald-400 border border-emerald-500/30">
                  Wallet
                </span>
              </span>
            </div>
          </Link>

          {/* Navigation links */}
          <nav className="hidden md:flex items-center gap-1">
            {navItems.map((item) => {
              const Icon = item.icon;
              const isActive = location.pathname === item.path;
              return (
                <Link
                  key={item.path}
                  to={item.path}
                  className={`flex items-center gap-2 px-3 py-2 rounded-lg text-sm font-medium transition-all ${
                    isActive
                      ? "bg-slate-800 text-white font-semibold"
                      : "text-slate-400 hover:text-slate-200 hover:bg-slate-800/50"
                  }`}
                >
                  <Icon className={`w-4 h-4 ${isActive ? "text-emerald-400" : ""}`} />
                  {item.name}
                </Link>
              );
            })}

            {/* Teasers for Phase 13/14 */}
            <span
              title="Coming in Phase 13"
              className="flex items-center gap-1.5 px-3 py-2 rounded-lg text-xs text-slate-500 cursor-not-allowed opacity-60"
            >
              <Cpu className="w-3.5 h-3.5" />
              Mining
            </span>
            <span
              title="Coming in Phase 14"
              className="flex items-center gap-1.5 px-3 py-2 rounded-lg text-xs text-slate-500 cursor-not-allowed opacity-60"
            >
              <Globe className="w-3.5 h-3.5" />
              Explorer
            </span>
          </nav>
        </div>

        {/* Right: Network status, User profile, Logout */}
        <div className="flex items-center gap-3 sm:gap-4">
          {/* Realtime WebSocket indicator */}
          <div
            title={
              isConnected
                ? `Connected to Node (Height: #${nodeStatus?.height ?? 0})`
                : "Connecting to WebSocket..."
            }
            className="flex items-center gap-2 px-2.5 py-1 rounded-full bg-slate-900 border border-slate-800 text-xs font-mono"
          >
            <Radio className={`w-3.5 h-3.5 ${isConnected ? "text-emerald-400 animate-pulse" : "text-amber-500"}`} />
            <span className="hidden sm:inline text-slate-400">
              {isConnected
                ? nodeStatus?.height !== undefined
                  ? `Block #${nodeStatus.height}`
                  : "Live Node"
                : "Connecting"}
            </span>
          </div>

          {/* User profile */}
          {user && (
            <div className="flex items-center gap-2 pl-2 border-l border-slate-800">
              <div className="flex items-center gap-2 text-sm text-slate-300">
                <div className="w-7 h-7 rounded-full bg-slate-800 border border-slate-700 flex items-center justify-center text-slate-300">
                  <UserIcon className="w-4 h-4 text-emerald-400" />
                </div>
                <span className="font-medium hidden sm:inline">{user.username}</span>
              </div>

              <button
                type="button"
                onClick={async () => {
                  try {
                    await logout();
                  } catch (err: any) {
                    alert(err?.message || "Failed to log out. Please check your network connection.");
                  }
                }}
                id="logout-btn"
                title="Log out"
                className="p-2 text-slate-400 hover:text-rose-400 rounded-lg hover:bg-slate-800/80 transition-colors"
              >
                <LogOut className="w-4 h-4" />
              </button>
            </div>
          )}
        </div>
      </div>

      {/* Mobile navigation row */}
      <div className="md:hidden flex items-center justify-around border-t border-slate-800/80 bg-slate-950/80 px-2 py-1.5">
        {navItems.map((item) => {
          const Icon = item.icon;
          const isActive = location.pathname === item.path;
          return (
            <Link
              key={item.path}
              to={item.path}
              className={`flex flex-col items-center py-1 px-3 rounded-lg text-xs font-medium ${
                isActive ? "text-emerald-400 font-bold" : "text-slate-400"
              }`}
            >
              <Icon className="w-4 h-4 mb-0.5" />
              {item.name}
            </Link>
          );
        })}
      </div>
    </header>
  );
};
