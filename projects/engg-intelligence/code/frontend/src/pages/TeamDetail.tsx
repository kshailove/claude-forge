import { useParams, useNavigate } from "react-router-dom";
import { ArrowLeft, Users } from "lucide-react";
import * as TabsPrimitive from "@radix-ui/react-tabs";
import { RAGBadge } from "@/components/RAGBadge";
import { PRHealthPanel } from "@/components/PRHealthPanel";
import { SprintHealthPanel } from "@/components/SprintHealthPanel";
import { IncidentLoadPanel } from "@/components/IncidentLoadPanel";
import { SlackSignalPanel } from "@/components/SlackSignalPanel";
import { MembersPanel } from "@/components/MembersPanel";
import { PageLoader } from "@/components/LoadingSpinner";
import { useTeamDetail } from "@/hooks/useTeamDetail";
import { cn } from "@/lib/utils";

const TABS = [
  { id: "pr-health", label: "PR Health" },
  { id: "sprint-health", label: "Sprint" },
  { id: "incident-load", label: "Incidents" },
  { id: "slack-signal", label: "Slack" },
  { id: "members", label: "Members" },
] as const;

type TabId = (typeof TABS)[number]["id"];

export function TeamDetail() {
  const { teamId } = useParams<{ teamId: string }>();
  const navigate = useNavigate();

  const { data, isLoading, error } = useTeamDetail(teamId ?? "");

  if (isLoading) return <PageLoader />;

  if (error || !data) {
    return (
      <div className="flex h-64 flex-col items-center justify-center gap-4">
        <p className="text-sm text-muted-foreground">Team not found.</p>
        <button
          onClick={() => navigate("/teams")}
          className="flex items-center gap-2 text-sm text-primary hover:underline"
        >
          <ArrowLeft className="h-4 w-4" />
          Back to Teams
        </button>
      </div>
    );
  }

  return (
    <div className="space-y-6">
      {/* Back + Header */}
      <div>
        <button
          onClick={() => navigate("/teams")}
          className="mb-4 flex items-center gap-1.5 text-sm text-muted-foreground hover:text-foreground"
        >
          <ArrowLeft className="h-4 w-4" />
          Teams
        </button>

        <div className="flex flex-wrap items-start justify-between gap-4">
          <div>
            <h1 className="text-3xl font-bold">{data.team_name}</h1>
            <div className="mt-2 flex items-center gap-4">
              <RAGBadge rag={data.composite.rag} showLabel size="md" />
              <span className="text-sm text-muted-foreground">
                Composite score:{" "}
                <span className="font-semibold tabular-nums">
                  {data.composite.score.toFixed(0)}
                </span>
                /100
              </span>
              <span className="flex items-center gap-1 text-sm text-muted-foreground">
                <Users className="h-4 w-4" />
                {data.member_count} engineers
              </span>
            </div>
          </div>

          {/* Sub-score pills */}
          <div className="flex flex-wrap gap-2">
            <SubScorePill label="PR" score={data.composite.pr_health_score} />
            <SubScorePill
              label="Sprint"
              score={data.composite.sprint_health_score}
            />
            <SubScorePill
              label="Incidents"
              score={data.composite.incident_load_score}
            />
            {!data.composite.slack_degraded && (
              <SubScorePill
                label="Slack"
                score={data.composite.slack_signal_score}
              />
            )}
          </div>
        </div>
      </div>

      {/* DORA summary strip */}
      {data.dora && (
        <div className="grid grid-cols-2 gap-3 rounded-xl border border-border bg-muted/30 p-4 sm:grid-cols-4">
          <DoraStat
            label="Deploy Freq"
            value={`${data.dora.deployment_frequency_per_day.toFixed(2)}/day`}
            band={data.dora.deployment_frequency_band}
          />
          <DoraStat
            label="Lead Time"
            value={
              data.dora.lead_time_band === "low"
                ? "No data"
                : data.dora.lead_time_band
            }
            band={data.dora.lead_time_band}
          />
          <DoraStat
            label="Change Fail Rate"
            value={
              data.dora.change_failure_rate_pct != null
                ? `${data.dora.change_failure_rate_pct.toFixed(1)}%`
                : "—"
            }
            band={data.dora.change_failure_rate_band}
          />
          <DoraStat
            label="MTTR"
            value={data.dora.mttr_band}
            band={data.dora.mttr_band}
          />
        </div>
      )}

      {/* Sub-tabs */}
      <TabsPrimitive.Root defaultValue="pr-health">
        <TabsPrimitive.List className="flex gap-1 rounded-lg border border-border bg-muted/50 p-1">
          {TABS.map((tab) => (
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

        <div className="mt-6">
          <TabsPrimitive.Content value="pr-health">
            <PRHealthPanel teamId={teamId ?? ""} />
          </TabsPrimitive.Content>
          <TabsPrimitive.Content value="sprint-health">
            <SprintHealthPanel teamId={teamId ?? ""} />
          </TabsPrimitive.Content>
          <TabsPrimitive.Content value="incident-load">
            <IncidentLoadPanel teamId={teamId ?? ""} />
          </TabsPrimitive.Content>
          <TabsPrimitive.Content value="slack-signal">
            <SlackSignalPanel teamId={teamId ?? ""} />
          </TabsPrimitive.Content>
          <TabsPrimitive.Content value="members">
            <MembersPanel teamId={teamId ?? ""} />
          </TabsPrimitive.Content>
        </div>
      </TabsPrimitive.Root>
    </div>
  );
}

interface SubScorePillProps {
  label: string;
  score: number | null | undefined;
}

function SubScorePill({ label, score }: SubScorePillProps) {
  return (
    <div className="flex items-center gap-1.5 rounded-full border border-border bg-card px-3 py-1 text-xs">
      <span className="text-muted-foreground">{label}</span>
      <span className="font-semibold tabular-nums">
        {score != null ? score.toFixed(0) : "—"}
      </span>
    </div>
  );
}

interface DoraStatProps {
  label: string;
  value: string;
  band: string;
}

const BAND_COLORS: Record<string, string> = {
  elite: "text-green-600",
  high: "text-blue-600",
  medium: "text-amber-600",
  low: "text-red-600",
};

function DoraStat({ label, value, band }: DoraStatProps) {
  return (
    <div>
      <p className="text-xs text-muted-foreground">{label}</p>
      <p className={cn("mt-0.5 font-semibold", BAND_COLORS[band] ?? "")}>
        {value}
      </p>
      <p className="text-xs capitalize text-muted-foreground">{band}</p>
    </div>
  );
}
