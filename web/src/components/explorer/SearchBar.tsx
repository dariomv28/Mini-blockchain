import React, { useState } from "react";
import { useNavigate } from "react-router-dom";
import { AlertCircle, ArrowRight, Loader2, Search, X } from "lucide-react";
import { searchExplorer } from "../../api/explorer";

interface SearchBarProps {
  className?: string;
  autoFocus?: boolean;
}

export const SearchBar: React.FC<SearchBarProps> = ({ className = "", autoFocus = false }) => {
  const [query, setQuery] = useState("");
  const [isSearching, setIsSearching] = useState(false);
  const [notFoundQuery, setNotFoundQuery] = useState<string | null>(null);
  const navigate = useNavigate();

  const getPlaceholder = () => {
    const trimmed = query.trim();
    if (trimmed.startsWith("PYC_")) return "Searching by PYC Address...";
    if (/^\d+$/.test(trimmed)) return "Searching by Block Height...";
    if (/^[0-9a-fA-F]{64}$/.test(trimmed)) return "Searching by Block Hash or TxID...";
    return "Search by Block Height / Hash / TxID / Address...";
  };

  const handleSearch = async (e?: React.FormEvent) => {
    if (e) e.preventDefault();
    const q = query.trim();
    if (!q) return;

    try {
      setIsSearching(true);
      setNotFoundQuery(null);
      const res = await searchExplorer(q);

      if (res.result_type !== "not_found" && res.target_url) {
        navigate(res.target_url);
        setQuery("");
      } else {
        setNotFoundQuery(q);
      }
    } catch {
      setNotFoundQuery(q);
    } finally {
      setIsSearching(false);
    }
  };

  return (
    <div className={`w-full relative ${className}`}>
      <form onSubmit={handleSearch} className="relative flex items-center">
        <div className="absolute left-4 pointer-events-none text-slate-500">
          <Search className="w-5 h-5 text-emerald-400" />
        </div>

        <input
          type="text"
          value={query}
          onChange={(e) => {
            setQuery(e.target.value);
            if (notFoundQuery) setNotFoundQuery(null);
          }}
          placeholder={getPlaceholder()}
          autoFocus={autoFocus}
          className="w-full pl-11 pr-24 py-3.5 bg-slate-900/90 border border-slate-700/80 rounded-2xl text-sm text-slate-100 placeholder-slate-500 focus:outline-none focus:ring-2 focus:ring-emerald-500/50 focus:border-emerald-500 shadow-inner font-mono tracking-tight transition-all"
        />

        <div className="absolute right-2 flex items-center gap-1">
          {query && (
            <button
              type="button"
              onClick={() => {
                setQuery("");
                setNotFoundQuery(null);
              }}
              className="p-1 text-slate-400 hover:text-slate-200 rounded-lg"
              title="Clear search"
            >
              <X className="w-4 h-4" />
            </button>
          )}

          <button
            type="submit"
            disabled={!query.trim() || isSearching}
            className="px-3 py-1.5 rounded-xl bg-gradient-to-r from-emerald-500 to-cyan-500 text-slate-950 font-bold text-xs flex items-center gap-1 transition-all hover:scale-105 active:scale-95 disabled:opacity-40 disabled:hover:scale-100 shadow-md shadow-emerald-500/20 cursor-pointer"
          >
            {isSearching ? (
              <Loader2 className="w-4 h-4 animate-spin" />
            ) : (
              <>
                <span>Search</span>
                <ArrowRight className="w-3.5 h-3.5" />
              </>
            )}
          </button>
        </div>
      </form>

      {/* Not Found Banner */}
      {notFoundQuery && (
        <div className="mt-2.5 px-4 py-2.5 rounded-xl bg-rose-500/10 border border-rose-500/30 text-rose-300 text-xs flex items-center justify-between animate-in fade-in slide-in-from-top-1">
          <div className="flex items-center gap-2">
            <AlertCircle className="w-4 h-4 text-rose-400 flex-shrink-0" />
            <span>
              No matching block, transaction, or address found for:{" "}
              <strong className="font-mono text-rose-200 break-all">{notFoundQuery}</strong>
            </span>
          </div>
          <button
            type="button"
            onClick={() => setNotFoundQuery(null)}
            className="ml-2 text-rose-400 hover:text-rose-200 underline text-[11px]"
          >
            Dismiss
          </button>
        </div>
      )}
    </div>
  );
};
