/**
 * TypeScript types that mirror the backend Pydantic v2 schemas exactly.
 */

// ---------------------------------------------------------------------------
// Auth
// ---------------------------------------------------------------------------

export interface LoginRequest {
  username: string;
  password: string;
}

export interface LoginResponse {
  access_token: string;
  refresh_token: string;
  token_type: string;
  user: {
    id: string;
    username: string;
    email: string;
    role: string;
    team_id: string | null;
  };
}

// ---------------------------------------------------------------------------
// Overview
// ---------------------------------------------------------------------------

export type RAG = "red" | "amber" | "green";

export interface TeamHealthCard {
  team_id: string;
  team_name: string;
  composite_score: number;
  rag: RAG;
  open_pr_count: number;
  sprint_completion_pct: number | null;
  active_incident_count: number;
  sparkline_7d: number[];
}

export interface OverviewResponse {
  teams: TeamHealthCard[];
  total: number;
}

// ---------------------------------------------------------------------------
// Teams list
// ---------------------------------------------------------------------------

export interface TeamSummary {
  team_id: string;
  team_name: string;
  slug: string;
  composite_score: number | null;
  rag: RAG | null;
  em_username: string | null;
  member_count: number;
}

export interface TeamsListResponse {
  teams: TeamSummary[];
  total: number;
}

// ---------------------------------------------------------------------------
// Team detail
// ---------------------------------------------------------------------------

export interface CompositeScoreDetail {
  score: number;
  rag: RAG;
  pr_health_score: number | null;
  sprint_health_score: number | null;
  incident_load_score: number | null;
  slack_signal_score: number | null;
  pr_health_weight: number;
  sprint_health_weight: number;
  incident_load_weight: number;
  slack_signal_weight: number;
  slack_degraded: boolean;
}

export interface DORAMetricsSummary {
  deployment_frequency: number;
  deployment_frequency_per_day: number;
  deployment_frequency_band: string;
  lead_time_for_changes_seconds: number | null;
  lead_time_band: string;
  change_failure_rate_pct: number | null;
  change_failure_rate_band: string;
  mttr_seconds: number | null;
  mttr_band: string;
  window_days: number;
  computed_at: string;
}

export interface MemberLoadIndicator {
  user_id: string;
  username: string;
  email: string;
  open_pr_count: number;
  on_call_hours_7d: number;
  active_incident_count: number;
  role: string;
}

export interface TeamDetailResponse {
  team_id: string;
  team_name: string;
  slug: string;
  composite: CompositeScoreDetail;
  dora: DORAMetricsSummary | null;
  members: MemberLoadIndicator[];
  member_count: number;
}

// ---------------------------------------------------------------------------
// PR Health
// ---------------------------------------------------------------------------

export interface StalePR {
  title: string;
  url: string;
  days_stale: number;
  author: string;
}

export interface PRHealthDetailResponse {
  team_id: string;
  score: number | null;
  rag: RAG | null;
  avg_cycle_time_seconds: number | null;
  p50_cycle_time_seconds: number | null;
  p95_cycle_time_seconds: number | null;
  avg_first_review_latency_seconds: number | null;
  p50_first_review_latency_seconds: number | null;
  stale_pr_count: number;
  review_coverage_pct: number | null;
  review_participation_pct: number | null;
  rework_rate_pct: number | null;
  merged_pr_count: number;
  open_pr_count: number;
  window_days: number;
  stale_prs: StalePR[];
}

export interface StalePRListResponse {
  team_id: string;
  stale_prs: StalePR[];
  total: number;
}

// ---------------------------------------------------------------------------
// Sprint Health
// ---------------------------------------------------------------------------

export interface SprintHealthDetailResponse {
  team_id: string;
  score: number | null;
  rag: RAG | null;
  current_sprint_name: string | null;
  current_sprint_id: string | null;
  current_sprint_completion_pct: number | null;
  scope_creep_pct: number | null;
  carry_over_rate_pct: number | null;
  blocked_ticket_count: number;
  blocked_avg_age_days: number | null;
  velocity_trend_points: number[];
  sprint_commitment_rate_pct: number | null;
  wip_count: number;
  flow_distribution: Record<string, number>;
  setup_required: boolean;
}

// ---------------------------------------------------------------------------
// Incident Load
// ---------------------------------------------------------------------------

export interface RepeatServiceItem {
  service_name: string;
  count: number;
}

export interface IncidentItem {
  id: string;
  title: string;
  severity: string;
  triggered_at: string;
  resolved_at: string | null;
  mttr_seconds: number | null;
  service_name: string | null;
}

export interface IncidentLoadDetailResponse {
  team_id: string;
  score: number | null;
  rag: RAG | null;
  incident_count: number;
  p1_count: number;
  p2_count: number;
  p3_count: number;
  p4_count: number;
  avg_mttr_seconds: number | null;
  p50_mttr_seconds: number | null;
  p95_mttr_seconds: number | null;
  avg_mtta_seconds: number | null;
  incidents_per_week: number;
  repeat_services: RepeatServiceItem[];
  window_days: number;
  recent_incidents: IncidentItem[];
}

// ---------------------------------------------------------------------------
// Engineers
// ---------------------------------------------------------------------------

export interface EngineerSummary {
  user_id: string;
  name: string;
  email: string;
  role: string;
  team_name: string | null;
  composite_load_indicator: "high" | "medium" | "low";
  pr_authored_30d: number;
  pr_merged_30d: number;
  tickets_closed_30d: number;
  incidents_paged_30d: number;
}

export interface EngineersListResponse {
  engineers: EngineerSummary[];
  total: number;
}

export interface CodeActivity {
  prs_authored: number;
  prs_merged: number;
  avg_cycle_time_seconds: number | null;
  pr_size_trend: number[];
}

export interface ReviewActivity {
  prs_reviewed: number;
  avg_first_review_latency_seconds: number | null;
  avg_review_depth: number | null;
}

export interface TaskDelivery {
  tickets_closed: number;
  avg_ticket_cycle_time_seconds: number | null;
  carry_over_count: number;
}

export interface EngineerIncidentLoad {
  pages_received: number;
  personal_avg_mttr_seconds: number | null;
  on_call_hours: number;
}

export interface ReviewPartner {
  user_id: string;
  name: string;
  review_count: number;
}

export interface EngineerCollaboration {
  top_review_partners: ReviewPartner[];
}

export interface EngineerDetailResponse {
  user_id: string;
  name: string;
  email: string;
  role: string;
  team_name: string | null;
  code_activity: CodeActivity;
  review_activity: ReviewActivity;
  task_delivery: TaskDelivery;
  incident_load: EngineerIncidentLoad;
  collaboration: EngineerCollaboration;
}

// ---------------------------------------------------------------------------
// Incidents (company-wide)
// ---------------------------------------------------------------------------

export interface IncidentListItem {
  id: string;
  title: string;
  severity: string;
  service_name: string | null;
  team_name: string | null;
  triggered_at: string;
  resolved_at: string | null;
  mttr_seconds: number | null;
}

export interface IncidentsListResponse {
  incidents: IncidentListItem[];
  total: number;
  page: number;
  page_size: number;
  total_pages: number;
}

export interface SeverityBreakdown {
  p1: number;
  p2: number;
  p3: number;
  p4: number;
}

export interface WorstIncident {
  id: string;
  title: string;
  severity: string;
  mttr_seconds: number | null;
  triggered_at: string;
}

export interface CorrelationSignal {
  detected: boolean;
  description: string | null;
  avg_lag_days: number | null;
}

export interface IncidentsSummaryResponse {
  total_count: number;
  by_severity: SeverityBreakdown;
  avg_mttr_seconds: number | null;
  worst_mttr_incident: WorstIncident | null;
  correlation_signal: CorrelationSignal;
  window_days: number;
}

export interface EngineerOncallLoad {
  user_id: string;
  name: string;
  on_call_hours: number;
  pages_received: number;
  team_name: string | null;
}

export interface OncallLoadResponse {
  engineers: EngineerOncallLoad[];
  gini_coefficient: number | null;
  window_days: number;
}

export interface ServiceIncidentStats {
  service_name: string;
  incident_count: number;
  p1_count: number;
  avg_mttr_seconds: number | null;
  repeat_count: number;
}

export interface IncidentsByServiceResponse {
  services: ServiceIncidentStats[];
  window_days: number;
}

export interface TimelineDay {
  date: string;
  count: number;
  p1_count: number;
}

export interface IncidentsTimelineResponse {
  timeline: TimelineDay[];
  window_days: number;
}

// ---------------------------------------------------------------------------
// Slack Signal
// ---------------------------------------------------------------------------

export interface SlackSignalDetailResponse {
  team_id: string;
  degraded: boolean;
  reason: string | null;
  score: number | null;
  rag: RAG | null;
}

// ---------------------------------------------------------------------------
// Team Members
// ---------------------------------------------------------------------------

export interface TeamMembersResponse {
  team_id: string;
  members: MemberLoadIndicator[];
  total: number;
}

// ---------------------------------------------------------------------------
// Digests
// ---------------------------------------------------------------------------

export interface DigestSummary {
  digest_id: string;
  digest_run_id: string;
  sent_at: string | null;
  subject: string;
  preview_text: string;
  delivery_status: string;
}

export interface DigestListResponse {
  digests: DigestSummary[];
  total: number;
}

export interface DigestDetailResponse {
  digest_id: string;
  digest_run_id: string;
  html_content: string;
  sent_at: string | null;
  subject: string;
  delivery_status: string;
}

export interface DigestPreviewResponse {
  html_content: string;
  generated_at: string;
  role_scope: string;
}
