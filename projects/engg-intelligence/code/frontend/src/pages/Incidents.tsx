import { useState } from "react";
import { AlertCircle, TrendingUp } from "lucide-react";
import * as TabsPrimitive from "@radix-ui/react-tabs";
import {
  AreaChart,
  Area,
  XAxis,
  YAxis,
  Tooltip,
  ResponsiveContainer,
  CartesianGrid,
} from "recharts";
import { MetricCard } from "@/components/MetricCard";
import { PageLoader } from "@/components/LoadingSpinner";
import {
  useIncidentsSummary,
  useIncidentsTimeline,
  useIncidentsByService,
  useOncallLoad,
  useIncidentsList,
} from "@/hooks/useIncidents";
import { formatSeconds, cn } from "@/lib/utils";
import type {
  ServiceIncidentStats,
  EngineerOncallLoad,
  IncidentListItem,
  TimelineDay,
} from "@/lib/types";

const WINDOW_OPTIONS = [30, 60, 90] as const;
type WindowDays = (typeof WINDOW_OPTIONS)[number];

const SEVERITY_COLORS: Record<string, string> = {
  p1: "bg-red-100 text-red-700",
  p2: "bg-orange-100 text-orange-700",
  p3: "bg-amber-100 text-amber-700",
  p4: "bg-green-100 text-green-700",
};

export function Incidents() {
  const [window, setWindow] = useState<WindowDays>(30);
  const [severityFilter, setSeverityFilter] = useState<string>("");
  const [page, setPage] = useState(1);

  const { data: summary, isLoading: summaryLoading } = useIncidentsSummary(window);
  const { data: timeline, isLoading: timelineLoading } = useIncidentsTimeline(window);

  if (summaryLoading || timelineLoading) return <PageLoader />;

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex flex-wrap items-start justify-between gap-4">
        <div>
          <h1 className="text-3xl font-bold">Incidents</h1>
          <p className="mt-1 text-sm text-muted-foreground">
            Company-wide incident health
          </p>
        </div>

        {/* Window selector */}
        <div className="flex items-center gap-1 rounded-lg border border-border bg-muted/50 p-1">
          {WINDOW_OPTIONS.map((w) => (
            <button
              key={w}
              onClick={() => setWindow(w)}
              className={cn(
                "rounded-md px-3 py-1.5 text-sm font-medium transition-colors",
                window === w
                  ? "bg-background text-foreground shadow-sm"
                  : "text-muted-foreground hover:text-foreground"
              )}
            >
              {w}d
            </button>
          ))}
        </div>
      </div>

      {/* Summary cards */}
      {summary && (
        <div className="grid grid-cols-2 gap-4 sm:grid-cols-4">
          <MetricCard
            label="Total Incidents"
            value={summary.total_count}
            subtitle={`Last ${window} days`}
          />
          <MetricCard
            label="Avg MTTR"
            value={formatSeconds(summary.avg_mttr_seconds)}
          />
          <MetricCard
            label="P1 Incidents"
            value={summary.by_severity.p1}
            valueClassName={summary.by_severity.p1 > 0 ? "text-red-600" : undefined}
          />
          <MetricCard
            label="P2 Incidents"
            value={summary.by_severity.p2}
            valueClassName={summary.by_severity.p2 > 3 ? "text-orange-600" : undefined}
          />
        </div>
      )}

      {/* Severity breakdown pills */}
      {summary && (
        <div className="flex flex-wrap gap-3">
          {(["p1", "p2", "p3", "p4"] as const).map((sev) => (
            <span
              key={sev}
              className={cn(
                "inline-flex items-center gap-1.5 rounded-full px-3 py-1.5 text-sm font-medium",
                SEVERITY_COLORS[sev]
              )}
            >
              {sev.toUpperCase()}: {summary.by_severity[sev]}
            </span>
          ))}
        </div>
      )}

      {/* Correlation callout */}
      {summary?.correlation_signal.detected && (
        <div className="flex items-start gap-3 rounded-xl border border-amber-200 bg-amber-50 p-4">
          <TrendingUp className="mt-0.5 h-5 w-5 shrink-0 text-amber-600" />
          <div>
            <p className="font-medium text-amber-800">Incident–Delivery Correlation Detected</p>
            <p className="mt-0.5 text-sm text-amber-700">
              {summary.correlation_signal.description}
            </p>
          </div>
        </div>
      )}

      {/* Worst incident callout */}
      {summary?.worst_mttr_incident && (
        <div className="flex items-start gap-3 rounded-xl border border-red-200 bg-red-50 p-4">
          <AlertCircle className="mt-0.5 h-5 w-5 shrink-0 text-red-600" />
          <div>
            <p className="font-medium text-red-800">Worst MTTR Incident</p>
            <p className="mt-0.5 text-sm text-red-700">
              <span
                className={cn(
                  "mr-2 inline-block rounded-full px-2 py-0.5 text-xs font-medium",
                  SEVERITY_COLORS[summary.worst_mttr_incident.severity] ??
                    "bg-gray-100 text-gray-700"
                )}
              >
                {summary.worst_mttr_incident.severity.toUpperCase()}
              </span>
              {summary.worst_mttr_incident.title}
              {" — MTTR: "}
              <strong>{formatSeconds(summary.worst_mttr_incident.mttr_seconds)}</strong>
            </p>
          </div>
        </div>
      )}

      {/* Timeline chart */}
      {timeline && timeline.timeline.length > 0 && (
        <div className="rounded-xl border border-border bg-card p-6">
          <h2 className="mb-4 text-lg font-semibold">Daily Incidents</h2>
          <ResponsiveContainer width="100%" height={200}>
            <AreaChart
              data={timeline.timeline}
              margin={{ top: 4, right: 4, left: -20, bottom: 0 }}
            >
              <defs>
                <linearGradient id="incidentGradient" x1="0" y1="0" x2="0" y2="1">
                  <stop offset="5%" stopColor="hsl(var(--primary))" stopOpacity={0.3} />
                  <stop offset="95%" stopColor="hsl(var(--primary))" stopOpacity={0} />
                </linearGradient>
                <linearGradient id="p1Gradient" x1="0" y1="0" x2="0" y2="1">
                  <stop offset="5%" stopColor="#ef4444" stopOpacity={0.3} />
                  <stop offset="95%" stopColor="#ef4444" stopOpacity={0} />
                </linearGradient>
              </defs>
              <CartesianGrid strokeDasharray="3 3" stroke="hsl(var(--border))" />
              <XAxis
                dataKey="date"
                tickFormatter={(d: string) => {
                  const dt = new Date(d);
                  return `${dt.getMonth() + 1}/${dt.getDate()}`;
                }}
                tick={{ fontSize: 11 }}
                tickLine={false}
                interval={Math.floor(timeline.timeline.length / 6)}
              />
              <YAxis tick={{ fontSize: 11 }} tickLine={false} axisLine={false} />
              <Tooltip
                formatter={(value: number, name: string) => [
                  value,
                  name === "count" ? "Total" : "P1",
                ]}
                labelFormatter={(label: string) => label}
              />
              <Area
                type="monotone"
                dataKey="count"
                stroke="hsl(var(--primary))"
                strokeWidth={2}
                fill="url(#incidentGradient)"
                name="count"
              />
              <Area
                type="monotone"
                dataKey="p1_count"
                stroke="#ef4444"
                strokeWidth={1.5}
                fill="url(#p1Gradient)"
                name="p1_count"
              />
            </AreaChart>
          </ResponsiveContainer>
          <div className="mt-2 flex gap-4 text-xs text-muted-foreground">
            <span className="flex items-center gap-1.5">
              <span className="h-2.5 w-2.5 rounded-sm bg-primary/60" />
              Total
            </span>
            <span className="flex items-center gap-1.5">
              <span className="h-2.5 w-2.5 rounded-sm bg-red-400" />
              P1
            </span>
          </div>
        </div>
      )}

      {/* Breakdowns sub-tabs */}
      <TabsPrimitive.Root defaultValue="by-service">
        <TabsPrimitive.List className="flex gap-1 rounded-lg border border-border bg-muted/50 p-1">
          {[
            { id: "by-service", label: "By Service" },
            { id: "oncall-load", label: "On-Call Load" },
            { id: "incident-list", label: "Incident List" },
          ].map((tab) => (
            <TabsPrimitive.Trigger
              key={tab.id}
              value={tab.id}
              className={cn(
                "flex-1 rounded-md px-4 py-2 text-sm font-medium transition-colors",
                "text-muted-foreground hover:text-foreground",
                "data-[state=active]:bg-background data-[state=active]:text-foreground data-[state=active]:shadow-sm"
              )}
            >
              {tab.label}
            </TabsPrimitive.Trigger>
          ))}
        </TabsPrimitive.List>

        <div className="mt-4">
          <TabsPrimitive.Content value="by-service">
            <ByServiceTab windowDays={window} />
          </TabsPrimitive.Content>
          <TabsPrimitive.Content value="oncall-load">
            <OncallLoadTab windowDays={window} />
          </TabsPrimitive.Content>
          <TabsPrimitive.Content value="incident-list">
            <IncidentListTab
              windowDays={window}
              severityFilter={severityFilter}
              onSeverityChange={(s) => {
                setSeverityFilter(s);
                setPage(1);
              }}
              page={page}
              onPageChange={setPage}
            />
          </TabsPrimitive.Content>
        </div>
      </TabsPrimitive.Root>
    </div>
  );
}

// ---------------------------------------------------------------------------
// By Service sub-tab
// ---------------------------------------------------------------------------

function ByServiceTab({ windowDays }: { windowDays: number }) {
  const { data, isLoading } = useIncidentsByService(windowDays);

  if (isLoading) return <PageLoader />;
  if (!data || data.services.length === 0)
    return (
      <p className="py-6 text-center text-sm text-muted-foreground">
        No service data available.
      </p>
    );

  return (
    <div className="overflow-x-auto rounded-xl border border-border">
      <table className="w-full text-sm">
        <thead className="bg-muted/50">
          <tr>
            <th className="px-4 py-3 text-left font-medium text-muted-foreground">Service</th>
            <th className="px-4 py-3 text-right font-medium text-muted-foreground">Total</th>
            <th className="px-4 py-3 text-right font-medium text-muted-foreground">P1</th>
            <th className="px-4 py-3 text-right font-medium text-muted-foreground">Avg MTTR</th>
            <th className="px-4 py-3 text-right font-medium text-muted-foreground">Repeat?</th>
          </tr>
        </thead>
        <tbody className="divide-y divide-border">
          {data.services.map((svc: ServiceIncidentStats) => (
            <tr key={svc.service_name} className="hover:bg-muted/30">
              <td className="px-4 py-3 font-medium">{svc.service_name}</td>
              <td className="px-4 py-3 text-right tabular-nums">{svc.incident_count}</td>
              <td className="px-4 py-3 text-right tabular-nums">
                {svc.p1_count > 0 ? (
                  <span className="font-medium text-red-600">{svc.p1_count}</span>
                ) : (
                  <span className="text-muted-foreground">0</span>
                )}
              </td>
              <td className="px-4 py-3 text-right tabular-nums">
                {formatSeconds(svc.avg_mttr_seconds)}
              </td>
              <td className="px-4 py-3 text-right">
                {svc.repeat_count > 0 ? (
                  <span className="rounded-full bg-amber-100 px-2 py-0.5 text-xs font-medium text-amber-700">
                    Repeat
                  </span>
                ) : (
                  <span className="text-muted-foreground">—</span>
                )}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

// ---------------------------------------------------------------------------
// On-call load sub-tab
// ---------------------------------------------------------------------------

function OncallLoadTab({ windowDays }: { windowDays: number }) {
  const { data, isLoading } = useOncallLoad(windowDays);

  if (isLoading) return <PageLoader />;
  if (!data || data.engineers.length === 0)
    return (
      <p className="py-6 text-center text-sm text-muted-foreground">
        No on-call data available.
      </p>
    );

  // Sort by pages_received descending
  const sorted = [...data.engineers].sort(
    (a, b) => b.pages_received - a.pages_received
  );

  const gini = data.gini_coefficient;
  const fairnessLabel =
    gini == null ? null
    : gini < 0.2 ? "Fair"
    : gini < 0.4 ? "Moderate"
    : "Unequal";
  const fairnessColor =
    gini == null ? ""
    : gini < 0.2 ? "text-green-600"
    : gini < 0.4 ? "text-amber-600"
    : "text-red-600";

  return (
    <div className="space-y-4">
      {gini != null && (
        <div className="flex items-center gap-3 rounded-lg border border-border bg-muted/30 px-4 py-3">
          <span className="text-sm text-muted-foreground">
            On-call fairness (Gini):
          </span>
          <span className={cn("font-semibold tabular-nums", fairnessColor)}>
            {gini.toFixed(3)}
          </span>
          {fairnessLabel && (
            <span className={cn("text-sm font-medium", fairnessColor)}>
              — {fairnessLabel}
            </span>
          )}
        </div>
      )}

      <div className="overflow-x-auto rounded-xl border border-border">
        <table className="w-full text-sm">
          <thead className="bg-muted/50">
            <tr>
              <th className="px-4 py-3 text-left font-medium text-muted-foreground">
                Engineer
              </th>
              <th className="px-4 py-3 text-left font-medium text-muted-foreground">
                Team
              </th>
              <th className="px-4 py-3 text-right font-medium text-muted-foreground">
                Pages Received
              </th>
              <th className="px-4 py-3 text-right font-medium text-muted-foreground">
                On-Call Hours
              </th>
            </tr>
          </thead>
          <tbody className="divide-y divide-border">
            {sorted.map((eng: EngineerOncallLoad) => (
              <tr key={eng.user_id} className="hover:bg-muted/30">
                <td className="px-4 py-3">
                  <div className="flex items-center gap-2.5">
                    <div className="flex h-7 w-7 shrink-0 items-center justify-center rounded-full bg-primary/10 text-xs font-semibold uppercase text-primary">
                      {eng.name[0] ?? "?"}
                    </div>
                    <span className="font-medium">{eng.name}</span>
                  </div>
                </td>
                <td className="px-4 py-3 text-muted-foreground">
                  {eng.team_name ?? "—"}
                </td>
                <td className="px-4 py-3 text-right tabular-nums">
                  {eng.pages_received > 0 ? (
                    <span className={eng.pages_received >= 5 ? "font-medium text-red-600" : ""}>
                      {eng.pages_received}
                    </span>
                  ) : (
                    <span className="text-muted-foreground">0</span>
                  )}
                </td>
                <td className="px-4 py-3 text-right tabular-nums">
                  {eng.on_call_hours.toFixed(1)}h
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Incident list sub-tab
// ---------------------------------------------------------------------------

interface IncidentListTabProps {
  windowDays: number;
  severityFilter: string;
  onSeverityChange: (s: string) => void;
  page: number;
  onPageChange: (p: number) => void;
}

function IncidentListTab({
  windowDays,
  severityFilter,
  onSeverityChange,
  page,
  onPageChange,
}: IncidentListTabProps) {
  const { data, isLoading } = useIncidentsList({
    window_days: windowDays,
    severity: severityFilter || undefined,
    page,
    page_size: 25,
  });

  return (
    <div className="space-y-4">
      {/* Severity filter */}
      <div className="flex flex-wrap items-center gap-2">
        <span className="text-sm text-muted-foreground">Filter:</span>
        {["", "p1", "p2", "p3", "p4"].map((sev) => (
          <button
            key={sev}
            onClick={() => onSeverityChange(sev)}
            className={cn(
              "rounded-full px-3 py-1 text-xs font-medium transition-colors",
              severityFilter === sev
                ? "bg-primary text-primary-foreground"
                : "border border-border hover:bg-muted",
              sev !== "" && SEVERITY_COLORS[sev]
            )}
          >
            {sev === "" ? "All" : sev.toUpperCase()}
          </button>
        ))}
      </div>

      {isLoading ? (
        <PageLoader />
      ) : !data || data.incidents.length === 0 ? (
        <p className="py-6 text-center text-sm text-muted-foreground">
          No incidents found.
        </p>
      ) : (
        <>
          <div className="overflow-x-auto rounded-xl border border-border">
            <table className="w-full text-sm">
              <thead className="bg-muted/50">
                <tr>
                  <th className="px-4 py-3 text-left font-medium text-muted-foreground">Sev</th>
                  <th className="px-4 py-3 text-left font-medium text-muted-foreground">Title</th>
                  <th className="px-4 py-3 text-left font-medium text-muted-foreground">Service</th>
                  <th className="px-4 py-3 text-left font-medium text-muted-foreground">Team</th>
                  <th className="px-4 py-3 text-right font-medium text-muted-foreground">MTTR</th>
                  <th className="px-4 py-3 text-left font-medium text-muted-foreground">Status</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-border">
                {data.incidents.map((inc: IncidentListItem) => (
                  <tr key={inc.id} className="hover:bg-muted/30">
                    <td className="px-4 py-3">
                      <span
                        className={cn(
                          "inline-block rounded-full px-2 py-0.5 text-xs font-medium",
                          SEVERITY_COLORS[inc.severity] ?? "bg-gray-100 text-gray-700"
                        )}
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
                    <td className="px-4 py-3 text-muted-foreground">
                      {inc.team_name ?? "—"}
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

          {/* Pagination */}
          {data.total_pages > 1 && (
            <div className="flex items-center justify-between text-sm">
              <span className="text-muted-foreground">
                Page {data.page} of {data.total_pages} ({data.total} total)
              </span>
              <div className="flex gap-2">
                <button
                  disabled={page <= 1}
                  onClick={() => onPageChange(page - 1)}
                  className="rounded-md border border-border px-3 py-1.5 disabled:opacity-40 hover:bg-muted"
                >
                  Previous
                </button>
                <button
                  disabled={page >= data.total_pages}
                  onClick={() => onPageChange(page + 1)}
                  className="rounded-md border border-border px-3 py-1.5 disabled:opacity-40 hover:bg-muted"
                >
                  Next
                </button>
              </div>
            </div>
          )}
        </>
      )}
    </div>
  );
}
