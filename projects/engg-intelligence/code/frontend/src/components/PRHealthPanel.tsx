import { ExternalLink } from "lucide-react";
import { RAGBadge } from "./RAGBadge";
import { MetricCard } from "./MetricCard";
import { PageLoader } from "./LoadingSpinner";
import { usePRHealth } from "@/hooks/useTeamDetail";
import { formatSeconds } from "@/lib/utils";

interface PRHealthPanelProps {
  teamId: string;
}

export function PRHealthPanel({ teamId }: PRHealthPanelProps) {
  const { data, isLoading, error } = usePRHealth(teamId);

  if (isLoading) return <PageLoader />;
  if (error || !data)
    return (
      <p className="py-8 text-center text-sm text-muted-foreground">
        Failed to load PR health data.
      </p>
    );

  return (
    <div className="space-y-6">
      {/* Score header */}
      <div className="flex items-center gap-3">
        <span className="text-4xl font-bold tabular-nums">
          {data.score != null ? data.score.toFixed(0) : "—"}
        </span>
        <div>
          <RAGBadge rag={data.rag} showLabel size="md" />
          <p className="text-xs text-muted-foreground">
            PR Health Score (30-day window)
          </p>
        </div>
      </div>

      {/* Key metrics */}
      <div className="grid grid-cols-2 gap-4 sm:grid-cols-3 lg:grid-cols-4">
        <MetricCard
          label="Avg Cycle Time"
          value={formatSeconds(data.avg_cycle_time_seconds)}
        />
        <MetricCard
          label="P50 Cycle Time"
          value={formatSeconds(data.p50_cycle_time_seconds)}
        />
        <MetricCard
          label="P95 Cycle Time"
          value={formatSeconds(data.p95_cycle_time_seconds)}
        />
        <MetricCard
          label="Avg Review Latency"
          value={formatSeconds(data.avg_first_review_latency_seconds)}
        />
        <MetricCard
          label="Review Coverage"
          value={data.review_coverage_pct?.toFixed(1) ?? "—"}
          unit="%"
        />
        <MetricCard
          label="Review Participation"
          value={data.review_participation_pct?.toFixed(1) ?? "—"}
          unit="%"
        />
        <MetricCard
          label="Rework Rate"
          value={data.rework_rate_pct?.toFixed(1) ?? "—"}
          unit="%"
        />
        <MetricCard label="Stale PRs" value={data.stale_pr_count} />
        <MetricCard label="Open PRs" value={data.open_pr_count} />
        <MetricCard label="Merged PRs" value={data.merged_pr_count} />
      </div>

      {/* Stale PR table */}
      {data.stale_prs.length > 0 && (
        <div>
          <h3 className="mb-3 font-medium">
            Stale Pull Requests ({data.stale_prs.length})
          </h3>
          <div className="overflow-x-auto rounded-lg border border-border">
            <table className="w-full text-sm">
              <thead className="bg-muted/50">
                <tr>
                  <th className="px-4 py-3 text-left font-medium text-muted-foreground">
                    Title
                  </th>
                  <th className="px-4 py-3 text-left font-medium text-muted-foreground">
                    Author
                  </th>
                  <th className="px-4 py-3 text-right font-medium text-muted-foreground">
                    Days Stale
                  </th>
                  <th className="px-4 py-3 text-left font-medium text-muted-foreground">
                    Link
                  </th>
                </tr>
              </thead>
              <tbody className="divide-y divide-border">
                {data.stale_prs.map((pr) => (
                  <tr key={pr.url} className="hover:bg-muted/30">
                    <td className="max-w-xs truncate px-4 py-3 font-medium">
                      {pr.title}
                    </td>
                    <td className="px-4 py-3 text-muted-foreground">
                      {pr.author}
                    </td>
                    <td className="px-4 py-3 text-right tabular-nums text-amber-600 font-medium">
                      {pr.days_stale.toFixed(1)}d
                    </td>
                    <td className="px-4 py-3">
                      <a
                        href={pr.url}
                        target="_blank"
                        rel="noopener noreferrer"
                        className="inline-flex items-center gap-1 text-primary hover:underline"
                        onClick={(e) => e.stopPropagation()}
                      >
                        <ExternalLink className="h-3.5 w-3.5" />
                        View
                      </a>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}
    </div>
  );
}
