import { RAGBadge } from "./RAGBadge";
import { MetricCard } from "./MetricCard";
import { PageLoader } from "./LoadingSpinner";
import { useIncidentLoad } from "@/hooks/useTeamDetail";
import { formatSeconds } from "@/lib/utils";

interface IncidentLoadPanelProps {
  teamId: string;
}

const SEVERITY_COLORS: Record<string, string> = {
  p1: "bg-red-100 text-red-700",
  p2: "bg-orange-100 text-orange-700",
  p3: "bg-amber-100 text-amber-700",
  p4: "bg-green-100 text-green-700",
};

export function IncidentLoadPanel({ teamId }: IncidentLoadPanelProps) {
  const { data, isLoading, error } = useIncidentLoad(teamId);

  if (isLoading) return <PageLoader />;
  if (error || !data)
    return (
      <p className="py-8 text-center text-sm text-muted-foreground">
        Failed to load incident load data.
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
            Incident Load Score ({data.window_days}-day window)
          </p>
        </div>
      </div>

      {/* Severity breakdown */}
      <div className="flex gap-3">
        {[
          { label: "P1", count: data.p1_count },
          { label: "P2", count: data.p2_count },
          { label: "P3", count: data.p3_count },
          { label: "P4", count: data.p4_count },
        ].map(({ label, count }) => (
          <span
            key={label}
            className={`inline-flex items-center gap-1.5 rounded-full px-3 py-1.5 text-sm font-medium ${
              SEVERITY_COLORS[label.toLowerCase()] ?? "bg-gray-100 text-gray-700"
            }`}
          >
            {label}: {count}
          </span>
        ))}
      </div>

      {/* Key metrics */}
      <div className="grid grid-cols-2 gap-4 sm:grid-cols-3 lg:grid-cols-4">
        <MetricCard label="Total Incidents" value={data.incident_count} />
        <MetricCard
          label="Incidents/Week"
          value={data.incidents_per_week.toFixed(1)}
        />
        <MetricCard
          label="Avg MTTR"
          value={formatSeconds(data.avg_mttr_seconds)}
        />
        <MetricCard
          label="P50 MTTR"
          value={formatSeconds(data.p50_mttr_seconds)}
        />
        <MetricCard
          label="P95 MTTR"
          value={formatSeconds(data.p95_mttr_seconds)}
        />
        <MetricCard
          label="Avg MTTA"
          value={formatSeconds(data.avg_mtta_seconds)}
        />
      </div>

      {/* Repeat offenders */}
      {data.repeat_services.length > 0 && (
        <div>
          <h3 className="mb-3 font-medium">
            Repeat Offenders (≥3 incidents)
          </h3>
          <div className="space-y-2">
            {data.repeat_services.map((svc) => (
              <div
                key={svc.service_name}
                className="flex items-center justify-between rounded-lg border border-border bg-muted/30 px-4 py-2.5"
              >
                <span className="font-medium">{svc.service_name}</span>
                <span className="rounded-full bg-red-100 px-2.5 py-0.5 text-xs font-semibold text-red-700">
                  {svc.count} incidents
                </span>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Recent incidents table */}
      {data.recent_incidents.length > 0 && (
        <div>
          <h3 className="mb-3 font-medium">
            Recent Incidents ({data.recent_incidents.length})
          </h3>
          <div className="overflow-x-auto rounded-lg border border-border">
            <table className="w-full text-sm">
              <thead className="bg-muted/50">
                <tr>
                  <th className="px-4 py-3 text-left font-medium text-muted-foreground">
                    Severity
                  </th>
                  <th className="px-4 py-3 text-left font-medium text-muted-foreground">
                    Title
                  </th>
                  <th className="px-4 py-3 text-left font-medium text-muted-foreground">
                    Service
                  </th>
                  <th className="px-4 py-3 text-right font-medium text-muted-foreground">
                    MTTR
                  </th>
                  <th className="px-4 py-3 text-left font-medium text-muted-foreground">
                    Status
                  </th>
                </tr>
              </thead>
              <tbody className="divide-y divide-border">
                {data.recent_incidents.map((inc) => (
                  <tr key={inc.id} className="hover:bg-muted/30">
                    <td className="px-4 py-3">
                      <span
                        className={`inline-block rounded-full px-2 py-0.5 text-xs font-medium ${
                          SEVERITY_COLORS[inc.severity] ??
                          "bg-gray-100 text-gray-700"
                        }`}
                      >
                        {inc.severity.toUpperCase()}
                      </span>
                    </td>
                    <td className="max-w-xs truncate px-4 py-3 font-medium">
                      {inc.title}
                    </td>
                    <td className="px-4 py-3 text-muted-foreground">
                      {inc.service_name ?? "—"}
                    </td>
                    <td className="px-4 py-3 text-right tabular-nums">
                      {formatSeconds(inc.mttr_seconds)}
                    </td>
                    <td className="px-4 py-3">
                      {inc.resolved_at ? (
                        <span className="text-green-600">Resolved</span>
                      ) : (
                        <span className="font-medium text-red-600">Active</span>
                      )}
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
