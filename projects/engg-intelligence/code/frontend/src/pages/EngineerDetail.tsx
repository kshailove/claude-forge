import { useParams, useNavigate } from "react-router-dom";
import { ArrowLeft } from "lucide-react";
import { MetricCard } from "@/components/MetricCard";
import { PageLoader } from "@/components/LoadingSpinner";
import { useEngineerDetail } from "@/hooks/useEngineers";
import { formatSeconds } from "@/lib/utils";
import type { ReviewPartner } from "@/lib/types";

export function EngineerDetail() {
  const { userId } = useParams<{ userId: string }>();
  const navigate = useNavigate();

  const { data, isLoading, error } = useEngineerDetail(userId ?? "");

  if (isLoading) return <PageLoader />;

  if (error || !data) {
    return (
      <div className="flex h-64 flex-col items-center justify-center gap-4">
        <p className="text-sm text-muted-foreground">Engineer not found.</p>
        <button
          onClick={() => navigate("/engineers")}
          className="flex items-center gap-2 text-sm text-primary hover:underline"
        >
          <ArrowLeft className="h-4 w-4" />
          Back to Engineers
        </button>
      </div>
    );
  }

  return (
    <div className="space-y-8">
      {/* Back + Header */}
      <div>
        <button
          onClick={() => navigate("/engineers")}
          className="mb-4 flex items-center gap-1.5 text-sm text-muted-foreground hover:text-foreground"
        >
          <ArrowLeft className="h-4 w-4" />
          Engineers
        </button>

        <div className="flex items-center gap-4">
          <div className="flex h-14 w-14 items-center justify-center rounded-full bg-primary/10 text-xl font-bold uppercase text-primary">
            {data.name[0] ?? "?"}
          </div>
          <div>
            <h1 className="text-3xl font-bold">{data.name}</h1>
            <p className="mt-0.5 text-sm text-muted-foreground">
              {data.email}
              {data.team_name && (
                <>
                  {" · "}
                  <span className="font-medium">{data.team_name}</span>
                </>
              )}
              {" · "}
              <span className="capitalize">{data.role}</span>
            </p>
          </div>
        </div>
      </div>

      {/* Code Activity */}
      <SectionCard title="Code Activity" subtitle="Last 30 days">
        <div className="grid grid-cols-2 gap-4 sm:grid-cols-4">
          <MetricCard label="PRs Authored" value={data.code_activity.prs_authored} />
          <MetricCard label="PRs Merged" value={data.code_activity.prs_merged} />
          <MetricCard
            label="Avg Cycle Time"
            value={formatSeconds(data.code_activity.avg_cycle_time_seconds)}
          />
          <MetricCard
            label="PR Size Trend"
            value={
              data.code_activity.pr_size_trend.length > 0
                ? `${data.code_activity.pr_size_trend.at(-1)?.toFixed(0)} lines`
                : null
            }
            subtitle="Latest 4-week avg"
          />
        </div>
        {data.code_activity.pr_size_trend.length === 4 && (
          <PRSizeTrend trend={data.code_activity.pr_size_trend} />
        )}
      </SectionCard>

      {/* Review Activity */}
      <SectionCard title="Review Activity" subtitle="Last 30 days">
        <div className="grid grid-cols-2 gap-4 sm:grid-cols-3">
          <MetricCard label="PRs Reviewed" value={data.review_activity.prs_reviewed} />
          <MetricCard
            label="Avg First Review Latency"
            value={formatSeconds(data.review_activity.avg_first_review_latency_seconds)}
          />
          <MetricCard
            label="Avg Review Depth"
            value={
              data.review_activity.avg_review_depth != null
                ? `${data.review_activity.avg_review_depth.toFixed(1)} comments`
                : null
            }
          />
        </div>
      </SectionCard>

      {/* Task Delivery */}
      <SectionCard title="Task Delivery" subtitle="Last 30 days">
        <div className="grid grid-cols-2 gap-4 sm:grid-cols-3">
          <MetricCard label="Tickets Closed" value={data.task_delivery.tickets_closed} />
          <MetricCard
            label="Avg Ticket Cycle Time"
            value={formatSeconds(data.task_delivery.avg_ticket_cycle_time_seconds)}
          />
          <MetricCard
            label="Carry-over Tickets"
            value={data.task_delivery.carry_over_count}
            subtitle="Incomplete at sprint end"
            valueClassName={
              data.task_delivery.carry_over_count > 0
                ? "text-amber-600"
                : undefined
            }
          />
        </div>
      </SectionCard>

      {/* Incident Load */}
      <SectionCard title="Incident Load" subtitle="Last 30 days">
        <div className="grid grid-cols-2 gap-4 sm:grid-cols-3">
          <MetricCard
            label="Pages Received"
            value={data.incident_load.pages_received}
            valueClassName={
              data.incident_load.pages_received >= 5 ? "text-red-600" : undefined
            }
          />
          <MetricCard
            label="Personal Avg MTTR"
            value={formatSeconds(data.incident_load.personal_avg_mttr_seconds)}
          />
          <MetricCard
            label="On-Call Hours"
            value={`${data.incident_load.on_call_hours.toFixed(1)}h`}
          />
        </div>
      </SectionCard>

      {/* Collaboration */}
      <SectionCard title="Collaboration" subtitle="Top review partners (last 30 days)">
        {data.collaboration.top_review_partners.length === 0 ? (
          <p className="text-sm text-muted-foreground">
            No review partners found in the last 30 days.
          </p>
        ) : (
          <div className="space-y-2">
            {data.collaboration.top_review_partners.map(
              (partner: ReviewPartner, idx: number) => (
                <div
                  key={partner.user_id}
                  className="flex items-center gap-3 rounded-lg border border-border bg-muted/20 px-4 py-3"
                >
                  <span className="w-6 shrink-0 text-sm font-medium text-muted-foreground">
                    #{idx + 1}
                  </span>
                  <div className="flex h-8 w-8 shrink-0 items-center justify-center rounded-full bg-primary/10 text-xs font-semibold uppercase text-primary">
                    {partner.name[0] ?? "?"}
                  </div>
                  <span className="flex-1 font-medium">{partner.name}</span>
                  <span className="rounded-full bg-primary/10 px-2.5 py-0.5 text-xs font-semibold text-primary">
                    {partner.review_count}{" "}
                    {partner.review_count === 1 ? "review" : "reviews"}
                  </span>
                </div>
              )
            )}
          </div>
        )}
      </SectionCard>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Sub-components
// ---------------------------------------------------------------------------

interface SectionCardProps {
  title: string;
  subtitle?: string;
  children: React.ReactNode;
}

function SectionCard({ title, subtitle, children }: SectionCardProps) {
  return (
    <div className="rounded-xl border border-border bg-card p-6 shadow-sm">
      <div className="mb-4">
        <h2 className="text-lg font-semibold">{title}</h2>
        {subtitle && (
          <p className="text-xs text-muted-foreground">{subtitle}</p>
        )}
      </div>
      {children}
    </div>
  );
}

function PRSizeTrend({ trend }: { trend: number[] }) {
  const max = Math.max(...trend, 1);
  const labels = ["W-4", "W-3", "W-2", "W-1"];

  return (
    <div className="mt-4">
      <p className="mb-2 text-xs font-medium text-muted-foreground">
        PR Size Trend (lines changed per week)
      </p>
      <div className="flex items-end gap-2">
        {trend.map((val, i) => (
          <div key={i} className="flex flex-1 flex-col items-center gap-1">
            <span className="text-xs tabular-nums text-muted-foreground">
              {val.toFixed(0)}
            </span>
            <div
              className="w-full rounded-t bg-primary/40"
              style={{ height: `${Math.max((val / max) * 60, 4)}px` }}
            />
            <span className="text-xs text-muted-foreground">{labels[i]}</span>
          </div>
        ))}
      </div>
    </div>
  );
}
