import { AlertCircle } from "lucide-react";
import { RAGBadge } from "./RAGBadge";
import { MetricCard } from "./MetricCard";
import { PageLoader } from "./LoadingSpinner";
import { useSlackSignal } from "@/hooks/useTeamDetail";

interface SlackSignalPanelProps {
  teamId: string;
}

export function SlackSignalPanel({ teamId }: SlackSignalPanelProps) {
  const { data, isLoading, error } = useSlackSignal(teamId);

  if (isLoading) return <PageLoader />;
  if (error || !data)
    return (
      <p className="py-8 text-center text-sm text-muted-foreground">
        Failed to load Slack signal data.
      </p>
    );

  if (data.degraded) {
    return (
      <div className="flex flex-col items-center gap-4 rounded-lg border border-amber-200 bg-amber-50 py-12 text-center">
        <AlertCircle className="h-10 w-10 text-amber-500" />
        <div>
          <p className="text-base font-medium text-amber-800">
            Slack Signal Unavailable
          </p>
          <p className="mt-1 text-sm text-amber-700">
            {data.reason ?? "Slack integration is not configured."}
          </p>
        </div>
        <p className="text-xs text-amber-600">
          Slack signal weight has been redistributed to other components.
        </p>
      </div>
    );
  }

  return (
    <div className="space-y-6">
      {/* Score header */}
      <div className="flex items-center gap-3">
        <span className="text-4xl font-bold tabular-nums">
          {data.score != null ? data.score.toFixed(0) : "—"}
        </span>
        <div>
          <RAGBadge rag={data.rag} showLabel size="md" />
          <p className="text-xs text-muted-foreground">Slack Signal Score</p>
        </div>
      </div>

      <div className="grid grid-cols-2 gap-4 sm:grid-cols-3">
        <MetricCard label="Score" value={data.score?.toFixed(0) ?? "—"} />
        <MetricCard label="Status" value={data.rag?.toUpperCase() ?? "—"} />
      </div>
    </div>
  );
}
