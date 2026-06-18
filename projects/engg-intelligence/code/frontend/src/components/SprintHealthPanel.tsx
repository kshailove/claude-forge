import {
  BarChart,
  Bar,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
} from "recharts";
import { RAGBadge } from "./RAGBadge";
import { MetricCard } from "./MetricCard";
import { PageLoader } from "./LoadingSpinner";
import { useSprintHealth } from "@/hooks/useTeamDetail";

interface SprintHealthPanelProps {
  teamId: string;
}

export function SprintHealthPanel({ teamId }: SprintHealthPanelProps) {
  const { data, isLoading, error } = useSprintHealth(teamId);

  if (isLoading) return <PageLoader />;
  if (error || !data)
    return (
      <p className="py-8 text-center text-sm text-muted-foreground">
        Failed to load sprint health data.
      </p>
    );

  if (data.setup_required) {
    return (
      <div className="flex flex-col items-center gap-4 py-16 text-center">
        <p className="text-lg font-medium">Sprint tracking not configured</p>
        <p className="text-sm text-muted-foreground">
          Connect a Jira or ClickUp integration and configure sprints to see
          sprint health metrics.
        </p>
      </div>
    );
  }

  const velocityChartData = data.velocity_trend_points.map((pts, i) => ({
    sprint: `S-${i + 1}`,
    points: pts,
  }));

  return (
    <div className="space-y-6">
      {/* Score header */}
      <div className="flex items-center gap-3">
        <span className="text-4xl font-bold tabular-nums">
          {data.score != null ? data.score.toFixed(0) : "—"}
        </span>
        <div>
          <RAGBadge rag={data.rag} showLabel size="md" />
          {data.current_sprint_name && (
            <p className="text-xs text-muted-foreground">
              Active: {data.current_sprint_name}
            </p>
          )}
        </div>
      </div>

      {/* Key metrics */}
      <div className="grid grid-cols-2 gap-4 sm:grid-cols-3 lg:grid-cols-4">
        <MetricCard
          label="Sprint Completion"
          value={data.current_sprint_completion_pct?.toFixed(1) ?? "—"}
          unit="%"
        />
        <MetricCard
          label="WIP Count"
          value={data.wip_count}
        />
        <MetricCard
          label="Blocked Tickets"
          value={data.blocked_ticket_count}
          valueClassName={data.blocked_ticket_count > 0 ? "text-red-600" : undefined}
        />
        <MetricCard
          label="Blocked Avg Age"
          value={data.blocked_avg_age_days?.toFixed(1) ?? "—"}
          unit="days"
        />
        <MetricCard
          label="Scope Creep"
          value={data.scope_creep_pct?.toFixed(1) ?? "—"}
          unit="%"
        />
        <MetricCard
          label="Carry-over Rate"
          value={data.carry_over_rate_pct?.toFixed(1) ?? "—"}
          unit="%"
        />
        <MetricCard
          label="Commitment Rate"
          value={data.sprint_commitment_rate_pct?.toFixed(1) ?? "—"}
          unit="%"
        />
      </div>

      {/* Velocity trend chart */}
      {velocityChartData.length > 0 && (
        <div>
          <h3 className="mb-3 font-medium">
            Velocity Trend (last {velocityChartData.length} sprints)
          </h3>
          <ResponsiveContainer width="100%" height={180}>
            <BarChart data={velocityChartData}>
              <CartesianGrid strokeDasharray="3 3" stroke="hsl(var(--border))" />
              <XAxis
                dataKey="sprint"
                tick={{ fontSize: 12 }}
                axisLine={false}
                tickLine={false}
              />
              <YAxis
                tick={{ fontSize: 12 }}
                axisLine={false}
                tickLine={false}
              />
              <Tooltip
                formatter={(v: number) => [`${v.toFixed(1)} pts`, "Velocity"]}
                contentStyle={{ fontSize: "12px", borderRadius: "6px" }}
              />
              <Bar dataKey="points" fill="#6366f1" radius={[4, 4, 0, 0]} />
            </BarChart>
          </ResponsiveContainer>
        </div>
      )}

      {/* Flow distribution */}
      {Object.keys(data.flow_distribution).length > 0 && (
        <div>
          <h3 className="mb-3 font-medium">Flow Distribution (last sprint)</h3>
          <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
            {Object.entries(data.flow_distribution).map(([type, pct]) => (
              <MetricCard
                key={type}
                label={type.replace("_", " ")}
                value={pct.toFixed(1)}
                unit="%"
              />
            ))}
          </div>
        </div>
      )}
    </div>
  );
}
