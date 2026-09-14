import React from "react";
import { ArrowDownLeft, ArrowUpRight, CheckCircle2, Clock } from "lucide-react";

interface StatusBadgeProps {
  status: "pending" | "confirmed";
}

export const StatusBadge: React.FC<StatusBadgeProps> = ({ status }) => {
  if (status === "pending") {
    return (
      <span className="inline-flex items-center gap-1.5 px-2.5 py-0.5 rounded-full text-xs font-semibold bg-amber-500/10 text-amber-400 border border-amber-500/30 animate-pulse-subtle">
        <Clock className="w-3 h-3" />
        Pending
      </span>
    );
  }

  return (
    <span className="inline-flex items-center gap-1.5 px-2.5 py-0.5 rounded-full text-xs font-semibold bg-emerald-500/10 text-emerald-400 border border-emerald-500/30">
      <CheckCircle2 className="w-3 h-3" />
      Confirmed
    </span>
  );
};

interface DirectionBadgeProps {
  direction: "sent" | "received";
}

export const DirectionBadge: React.FC<DirectionBadgeProps> = ({ direction }) => {
  if (direction === "sent") {
    return (
      <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded text-xs font-medium bg-rose-500/10 text-rose-400 border border-rose-500/20">
        <ArrowUpRight className="w-3 h-3" />
        Sent
      </span>
    );
  }

  return (
    <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded text-xs font-medium bg-emerald-500/10 text-emerald-400 border border-emerald-500/20">
      <ArrowDownLeft className="w-3 h-3" />
      Received
    </span>
  );
};
