import React, { useState } from "react";
import { Link } from "react-router-dom";
import { Check, Copy, ExternalLink } from "lucide-react";

interface HashLinkProps {
  value: string;
  type: "block" | "tx" | "address";
  truncate?: boolean;
  truncateLength?: number;
  className?: string;
  showCopy?: boolean;
}

export const HashLink: React.FC<HashLinkProps> = ({
  value,
  type,
  truncate = true,
  truncateLength = 8,
  className = "",
  showCopy = true,
}) => {
  const [copied, setCopied] = useState(false);

  if (!value) return <span className="text-slate-500 font-mono text-xs">N/A</span>;

  const displayValue =
    truncate && value.length > truncateLength * 2
      ? `${value.slice(0, truncateLength)}...${value.slice(-truncateLength)}`
      : value;

  const path =
    type === "block"
      ? `/explorer/block/${value}`
      : type === "tx"
      ? `/explorer/tx/${value}`
      : `/explorer/address/${value}`;

  const handleCopy = async (e: React.MouseEvent) => {
    e.preventDefault();
    e.stopPropagation();
    try {
      await navigator.clipboard.writeText(value);
      setCopied(true);
      setTimeout(() => setCopied(false), 1500);
    } catch {
      // Fallback ignore
    }
  };

  return (
    <span className={`inline-flex items-center gap-1.5 font-mono text-xs ${className}`}>
      <Link
        to={path}
        title={value}
        className="text-emerald-400 hover:text-emerald-300 hover:underline inline-flex items-center gap-1 transition-colors"
      >
        <span>{displayValue}</span>
        <ExternalLink className="w-3 h-3 opacity-50 hover:opacity-100 flex-shrink-0" />
      </Link>

      {showCopy && (
        <button
          type="button"
          onClick={handleCopy}
          title={copied ? "Copied!" : "Copy full string"}
          className="p-1 rounded text-slate-400 hover:text-slate-200 hover:bg-slate-800 transition-colors"
        >
          {copied ? (
            <Check className="w-3 h-3 text-emerald-400" />
          ) : (
            <Copy className="w-3 h-3" />
          )}
        </button>
      )}
    </span>
  );
};
