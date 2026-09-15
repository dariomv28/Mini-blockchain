import React, { useEffect, useRef, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { AlertCircle, ArrowLeft, ChevronRight, Loader2 } from "lucide-react";
import { getBlockByHash, getBlockByHeight } from "../api/explorer";
import { ExplorerBlockDetail } from "../types/explorer";
import { BlockSummary } from "../components/explorer/BlockSummary";
import { TransactionTable } from "../components/explorer/TransactionTable";

export const BlockDetailPage: React.FC = () => {
  const { id } = useParams<{ id: string }>();
  const [block, setBlock] = useState<ExplorerBlockDetail | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const currentIdRef = useRef(id);
  currentIdRef.current = id;

  useEffect(() => {
    let isCurrent = true;

    const fetchBlock = async () => {
      if (!id) return;
      try {
        setIsLoading(true);
        setError(null);
        let data: ExplorerBlockDetail;
        if (/^\d+$/.test(id)) {
          data = await getBlockByHeight(parseInt(id, 10));
        } else {
          data = await getBlockByHash(id);
        }
        if (!isCurrent || currentIdRef.current !== id) return;
        setBlock(data);
      } catch (err: any) {
        if (!isCurrent || currentIdRef.current !== id) return;
        setError(err?.message || "Failed to load block detail");
      } finally {
        if (isCurrent && currentIdRef.current === id) {
          setIsLoading(false);
        }
      }
    };

    fetchBlock();

    return () => {
      isCurrent = false;
    };
  }, [id]);

  if (isLoading) {
    return (
      <div className="py-24 text-center">
        <Loader2 className="w-8 h-8 mx-auto animate-spin text-emerald-400 mb-3" />
        <p className="text-sm font-semibold text-slate-300 font-mono">
          Loading block data...
        </p>
      </div>
    );
  }

  if (error || !block) {
    return (
      <div className="space-y-6 py-12 max-w-2xl mx-auto text-center">
        <div className="w-12 h-12 rounded-2xl bg-rose-500/10 border border-rose-500/30 flex items-center justify-center text-rose-400 mx-auto">
          <AlertCircle className="w-6 h-6" />
        </div>
        <div>
          <h2 className="text-xl font-bold text-white">Block Not Found</h2>
          <p className="text-sm text-slate-400 mt-1">{error || "Block does not exist"}</p>
        </div>
        <Link
          to="/explorer"
          className="inline-flex items-center gap-2 px-4 py-2 rounded-xl bg-slate-800 text-slate-200 hover:bg-slate-700 text-xs font-semibold"
        >
          <ArrowLeft className="w-4 h-4" />
          Back to Explorer
        </Link>
      </div>
    );
  }

  return (
    <div className="space-y-6 animate-in fade-in duration-500 pb-12">
      {/* Breadcrumb Navigation */}
      <nav className="flex items-center gap-2 text-xs font-mono text-slate-400">
        <Link to="/explorer" className="hover:text-emerald-400 transition-colors">
          Explorer
        </Link>
        <ChevronRight className="w-3.5 h-3.5 text-slate-600" />
        <span className="text-slate-200 font-bold">Block #{block.height}</span>
      </nav>

      {/* Block Header Summary */}
      <BlockSummary block={block} />

      {/* Included Transactions List */}
      <section className="space-y-4">
        <div className="flex items-center justify-between">
          <h2 className="text-lg font-bold text-white flex items-center gap-2">
            Included Transactions
            <span className="text-xs font-mono px-2 py-0.5 rounded-full bg-slate-800 border border-slate-700 text-slate-300">
              {block.transactions.length}
            </span>
          </h2>
        </div>

        <TransactionTable transactions={block.transactions} />
      </section>
    </div>
  );
};
