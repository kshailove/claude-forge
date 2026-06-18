import { useNavigate } from "react-router-dom";
import { GitPullRequest, Zap, AlertTriangle } from "lucide-react";
import { RAGBadge } from "./RAGBadge";
import { SparklineChart } from "./SparklineChart";
import { cn } from "@/lib/utils";
import type { TeamHealthCard as TeamHealthCardType } from "@/lib/types";

interface TeamHealthCardProps {
  card: TeamHealthCardType;
  large?: boolean;
}

const RAG_SCORE_COLORS: Record<string, string> = {
  green: "text-green-600",
  amber: "text-amber-600",
  red: "text-red-600",
};

const RAG_SPARKLINE_COLORS: Record<string, string> = {
  green: "#22c55e",
  amber: "#f59e0b",
  red: "#ef4444",
};

const RAG_BORDER: Record<string, string> = {
  green: "border-green-200",
  amber: "border-amber-200",
  red: "border-red-200",
};

export function TeamHealthCard({ card, large = false }: TeamHealthCardProps) {
  const navigate = useNavigate();

  const scoreColor = RAG_SCORE_COLORS[card.rag] ?? "text-foreground";
  const sparklineColor = RAG_SPARKLINE_COLORS[card.rag] ?? "#6366f1";
  const borderColor = RAG_BORDER[card.rag] ?? "border-border";

  return (
    <button
      type="button"
      onClick={() => navigate(`/teams/${card.team_id}`)}
      className={cn(
        "w-full text-left rounded-xl border-2 bg-card shadow-sm",
        "transition-all duration-200 hover:shadow-md hover:-translate-y-0.5",
        "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring",
        borderColor,
        large ? "p-8" : "p-5"
      )}
    >
      {/* Header */}
      <div className="flex items-start justify-between gap-4">
        <div className="min-w-0">
          <h2
            className={cn(
              "truncate font-semibold",
              large ? "text-2xl" : "text-base"
            )}
          >
            {card.team_name}
          </h2>
          <RAGBadge rag={card.rag} showLabel size="sm" className="mt-1" />
        </div>

        {/* Composite score */}
        <div className="shrink-0 text-right">
          <p
            className={cn(
              "font-bold tabular-nums leading-none",
              large ? "text-6xl" : "text-4xl",
              scoreColor
            )}
          >
            {card.composite_score.toFixed(0)}
          </p>
          <p className="mt-1 text-xs text-muted-foreground">/ 100</p>
        </div>
      </div>

      {/* Stats row */}
      <div className="mt-4 grid grid-cols-3 gap-3">
        <Stat
          icon={<GitPullRequest className="h-3.5 w-3.5" />}
          label="Open PRs"
          value={String(card.open_pr_count)}
        />
        <Stat
          icon={<Zap className="h-3.5 w-3.5" />}
          label="Sprint"
          value={
            card.sprint_completion_pct != null
              ? `${card.sprint_completion_pct.toFixed(0)}%`
              : "—"
          }
        />
        <Stat
          icon={<AlertTriangle className="h-3.5 w-3.5" />}
          label="Incidents"
          value={String(card.active_incident_count)}
          valueClass={card.active_incident_count > 0 ? "text-red-600" : undefined}
        />
      </div>

      {/* Sparkline */}
      <div className="mt-4">
        <p className="mb-1 text-xs text-muted-foreground">7-day trend</p>
        <SparklineChart data={card.sparkline_7d} color={sparklineColor} height={36} />
      </div>
    </button>
  );
}

interface StatProps {
  icon: React.ReactNode;
  label: string;
  value: string;
  valueClass?: string;
}

function Stat({ icon, label, value, valueClass }: StatProps) {
  return (
    <div className="flex flex-col gap-0.5">
      <div className="flex items-center gap-1 text-muted-foreground">
        {icon}
        <span className="text-xs">{label}</span>
      </div>
      <span className={cn("text-sm font-semibold tabular-nums", valueClass)}>
        {value}
      </span>
    </div>
  );
}
