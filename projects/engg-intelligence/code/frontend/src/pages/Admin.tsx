import { useState, useRef } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query"; // useQueryClient used in TeamManagementSection
import { CheckCircle, XCircle, Github, RefreshCw, Plus, Pencil, X, Check, ChevronDown } from "lucide-react";
import apiClient from "@/lib/apiClient";
import { useAuthStore } from "@/stores/authStore";
import { LoadingSpinner } from "@/components/LoadingSpinner";
import { cn } from "@/lib/utils";

// ── Types ────────────────────────────────────────────────────────────────────

interface GitHubStatus {
  connected: boolean;
  status: string;
  last_synced_at: string | null;
  org_name: string | null;
  release_tag_pattern: string | null;
  integration_id: string | null;
}

interface AdminTeam {
  id: string;
  name: string;
  slug: string;
  em_user_id: string | null;
  created_at: string;
  updated_at: string;
}

interface BackfillJob {
  id: string;
  integration_id: string;
  integration_type: string;
  status: "pending" | "running" | "completed" | "failed";
  date_from: string;
  date_to: string;
  records_processed: number;
  records_total: number | null;
  last_checkpoint: string | null;
  error_message: string | null;
  started_at: string | null;
  completed_at: string | null;
  created_at: string;
}

// ── Shared UI primitives ─────────────────────────────────────────────────────

function SectionCard({ title, subtitle, children }: { title: string; subtitle?: string; children: React.ReactNode }) {
  return (
    <div className="rounded-xl border border-border bg-card shadow-sm">
      <div className="border-b border-border px-6 py-4">
        <h2 className="text-base font-semibold">{title}</h2>
        {subtitle && <p className="mt-0.5 text-sm text-muted-foreground">{subtitle}</p>}
      </div>
      <div className="p-6">{children}</div>
    </div>
  );
}

function StatusPill({ connected }: { connected: boolean }) {
  return (
    <span className={cn(
      "inline-flex items-center gap-1.5 rounded-full px-2.5 py-0.5 text-xs font-medium",
      connected
        ? "bg-green-500/10 text-green-600 dark:text-green-400"
        : "bg-muted text-muted-foreground"
    )}>
      {connected
        ? <CheckCircle className="h-3 w-3" />
        : <XCircle className="h-3 w-3" />}
      {connected ? "Connected" : "Disconnected"}
    </span>
  );
}

function ErrorBanner({ message }: { message: string }) {
  return (
    <div className="rounded-md bg-destructive/10 px-3 py-2.5 text-sm text-destructive">
      {message}
    </div>
  );
}

function SuccessBanner({ message }: { message: string }) {
  return (
    <div className="rounded-md bg-green-500/10 px-3 py-2.5 text-sm text-green-700 dark:text-green-400">
      {message}
    </div>
  );
}

function inputClass(className?: string) {
  return cn(
    "w-full rounded-md border border-input bg-background px-3 py-2 text-sm shadow-sm",
    "placeholder:text-muted-foreground focus:outline-none focus:ring-2 focus:ring-ring",
    "disabled:opacity-50",
    className
  );
}

function PrimaryButton({ children, loading, disabled, onClick, type = "button", className }: {
  children: React.ReactNode;
  loading?: boolean;
  disabled?: boolean;
  onClick?: () => void;
  type?: "button" | "submit";
  className?: string;
}) {
  return (
    <button
      type={type}
      onClick={onClick}
      disabled={disabled || loading}
      className={cn(
        "inline-flex items-center gap-2 rounded-md bg-primary px-4 py-2 text-sm font-medium",
        "text-primary-foreground shadow-sm transition-colors hover:bg-primary/90",
        "focus:outline-none focus:ring-2 focus:ring-ring disabled:cursor-not-allowed disabled:opacity-60",
        className
      )}
    >
      {loading && <LoadingSpinner size="sm" />}
      {children}
    </button>
  );
}

function GhostButton({ children, onClick, className }: {
  children: React.ReactNode;
  onClick?: () => void;
  className?: string;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      className={cn(
        "inline-flex items-center gap-1.5 rounded-md px-3 py-2 text-sm font-medium",
        "text-muted-foreground transition-colors hover:bg-accent hover:text-foreground",
        "focus:outline-none focus:ring-2 focus:ring-ring",
        className
      )}
    >
      {children}
    </button>
  );
}

// ── Section 1: GitHub Connect ─────────────────────────────────────────────────

function GitHubConnectSection() {
  const qc = useQueryClient();
  const [pat, setPat] = useState("");
  const [orgName, setOrgName] = useState("");
  const [tagPattern, setTagPattern] = useState("v*");
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState<string | null>(null);

  const { data: ghStatus, isLoading } = useQuery<GitHubStatus>({
    queryKey: ["admin", "github-status"],
    queryFn: async () => {
      const { data } = await apiClient.get<GitHubStatus>("/admin/integrations/github/status");
      return data;
    },
    refetchInterval: 30_000,
  });

  const connectMutation = useMutation({
    mutationFn: async () => {
      const { data } = await apiClient.post("/admin/integrations/github/connect", {
        personal_access_token: pat,
        org_name: orgName,
        release_tag_pattern: tagPattern || ".*",
      });
      return data;
    },
    onSuccess: () => {
      setSuccess(`Connected to GitHub org "${orgName}" successfully.`);
      setError(null);
      setPat("");
      qc.invalidateQueries({ queryKey: ["admin", "github-status"] });
    },
    onError: (err: unknown) => {
      const msg = extractErrorMessage(err) ?? "Failed to connect GitHub. Check your PAT and org name.";
      setError(msg);
      setSuccess(null);
    },
  });

  function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setError(null);
    setSuccess(null);
    if (!pat.trim()) { setError("Personal access token is required."); return; }
    if (!orgName.trim()) { setError("GitHub organisation name is required."); return; }
    connectMutation.mutate();
  }

  return (
    <SectionCard
      title="GitHub Connection"
      subtitle="Authorise access to your GitHub organisation so the platform can ingest PR, commit, and release data."
    >
      {isLoading ? (
        <LoadingSpinner size="sm" />
      ) : (
        <div className="mb-5 flex items-center gap-3">
          <Github className="h-5 w-5 text-muted-foreground" />
          <div>
            <StatusPill connected={ghStatus?.connected ?? false} />
            {ghStatus?.connected && ghStatus.org_name && (
              <p className="mt-0.5 text-xs text-muted-foreground">
                Org: <span className="font-medium text-foreground">{ghStatus.org_name}</span>
                {ghStatus.last_synced_at && (
                  <> · Last synced {formatRelative(ghStatus.last_synced_at)}</>
                )}
              </p>
            )}
          </div>
        </div>
      )}

      <form onSubmit={handleSubmit} className="space-y-4">
        <div className="grid gap-4 sm:grid-cols-2">
          <div>
            <label className="mb-1.5 block text-sm font-medium">
              GitHub Organisation <span className="text-destructive">*</span>
            </label>
            <input
              type="text"
              placeholder="acme-corp"
              value={orgName}
              onChange={(e) => setOrgName(e.target.value)}
              className={inputClass()}
            />
            <p className="mt-1 text-xs text-muted-foreground">
              The GitHub org slug (e.g. <code>acme-corp</code>, not a full URL).
            </p>
          </div>

          <div>
            <label className="mb-1.5 block text-sm font-medium">
              Release tag pattern
            </label>
            <input
              type="text"
              placeholder="v*"
              value={tagPattern}
              onChange={(e) => setTagPattern(e.target.value)}
              className={inputClass()}
            />
            <p className="mt-1 text-xs text-muted-foreground">
              Glob pattern to identify release tags (e.g. <code>v*</code>, <code>release-*</code>).
            </p>
          </div>
        </div>

        <div>
          <label className="mb-1.5 block text-sm font-medium">
            Personal Access Token <span className="text-destructive">*</span>
          </label>
          <input
            type="password"
            placeholder="github_pat_…"
            value={pat}
            onChange={(e) => setPat(e.target.value)}
            autoComplete="off"
            className={inputClass()}
          />
          <p className="mt-1 text-xs text-muted-foreground">
            Needs <code>repo</code> + <code>read:org</code> scopes (classic), or Contents/PRs/Metadata/Members read (fine-grained). Stored encrypted at rest.
          </p>
        </div>

        {error && <ErrorBanner message={error} />}
        {success && <SuccessBanner message={success} />}

        <PrimaryButton type="submit" loading={connectMutation.isPending}>
          <Github className="h-4 w-4" />
          {ghStatus?.connected ? "Update connection" : "Connect GitHub"}
        </PrimaryButton>
      </form>
    </SectionCard>
  );
}

// ── Section 2: Team Management ────────────────────────────────────────────────

interface EditingTeam { id: string; name: string; slug: string }
interface NewTeamDraft { name: string; slug: string }

function TeamManagementSection() {
  const qc = useQueryClient();
  const [editing, setEditing] = useState<EditingTeam | null>(null);
  const [showNewRow, setShowNewRow] = useState(false);
  const [newDraft, setNewDraft] = useState<NewTeamDraft>({ name: "", slug: "" });
  const [rowError, setRowError] = useState<string | null>(null);
  const nameRef = useRef<HTMLInputElement>(null);

  const { data, isLoading } = useQuery<{ teams: AdminTeam[]; total: number }>({
    queryKey: ["admin", "teams"],
    queryFn: async () => {
      const { data } = await apiClient.get<{ teams: AdminTeam[]; total: number }>("/admin/teams");
      return data;
    },
  });

  const updateMutation = useMutation({
    mutationFn: async ({ id, name, slug }: EditingTeam) => {
      await apiClient.put(`/admin/teams/${id}`, { name, slug });
    },
    onSuccess: () => {
      setEditing(null);
      setRowError(null);
      qc.invalidateQueries({ queryKey: ["admin", "teams"] });
    },
    onError: (err: unknown) => setRowError(extractErrorMessage(err) ?? "Update failed."),
  });

  const createMutation = useMutation({
    mutationFn: async (draft: NewTeamDraft) => {
      await apiClient.post("/admin/teams", { name: draft.name, slug: draft.slug });
    },
    onSuccess: () => {
      setShowNewRow(false);
      setNewDraft({ name: "", slug: "" });
      setRowError(null);
      qc.invalidateQueries({ queryKey: ["admin", "teams"] });
    },
    onError: (err: unknown) => setRowError(extractErrorMessage(err) ?? "Create failed."),
  });

  function startEdit(team: AdminTeam) {
    setEditing({ id: team.id, name: team.name, slug: team.slug });
    setShowNewRow(false);
    setRowError(null);
  }

  function cancelEdit() { setEditing(null); setRowError(null); }

  function saveEdit() {
    if (!editing) return;
    if (!editing.name.trim()) { setRowError("Name is required."); return; }
    if (!editing.slug.trim()) { setRowError("Slug is required."); return; }
    updateMutation.mutate(editing);
  }

  function openNewRow() {
    setShowNewRow(true);
    setEditing(null);
    setRowError(null);
    setNewDraft({ name: "", slug: "" });
    setTimeout(() => nameRef.current?.focus(), 50);
  }

  function saveNew() {
    if (!newDraft.name.trim()) { setRowError("Name is required."); return; }
    if (!newDraft.slug.trim()) { setRowError("Slug is required (e.g. platform-eng)."); return; }
    createMutation.mutate(newDraft);
  }

  // Auto-generate slug from name
  function handleNewName(name: string) {
    const slug = name.toLowerCase().replace(/[^a-z0-9]+/g, "-").replace(/^-|-$/g, "");
    setNewDraft({ name, slug });
  }

  return (
    <SectionCard
      title="Team Management"
      subtitle="Define teams that repos will be attributed to during backfill. Each team's slug is the stable identifier used internally."
    >
      {isLoading ? (
        <LoadingSpinner size="sm" />
      ) : (
        <>
          <div className="overflow-hidden rounded-lg border border-border">
            <table className="w-full text-sm">
              <thead className="border-b border-border bg-muted/40">
                <tr>
                  <th className="px-4 py-3 text-left font-medium text-muted-foreground">Team name</th>
                  <th className="px-4 py-3 text-left font-medium text-muted-foreground">Slug</th>
                  <th className="w-20 px-4 py-3 text-right font-medium text-muted-foreground">Actions</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-border">
                {data?.teams.map((team) =>
                  editing?.id === team.id ? (
                    <tr key={team.id} className="bg-accent/30">
                      <td className="px-4 py-2">
                        <input
                          autoFocus
                          value={editing.name}
                          onChange={(e) => setEditing({ ...editing, name: e.target.value })}
                          className={inputClass("py-1.5")}
                          onKeyDown={(e) => { if (e.key === "Enter") saveEdit(); if (e.key === "Escape") cancelEdit(); }}
                        />
                      </td>
                      <td className="px-4 py-2">
                        <input
                          value={editing.slug}
                          onChange={(e) => setEditing({ ...editing, slug: e.target.value })}
                          className={inputClass("py-1.5 font-mono text-xs")}
                          onKeyDown={(e) => { if (e.key === "Enter") saveEdit(); if (e.key === "Escape") cancelEdit(); }}
                        />
                      </td>
                      <td className="px-4 py-2 text-right">
                        <div className="flex items-center justify-end gap-1">
                          <button
                            onClick={saveEdit}
                            disabled={updateMutation.isPending}
                            className="rounded p-1 text-green-600 hover:bg-green-500/10 disabled:opacity-50"
                            title="Save"
                          >
                            {updateMutation.isPending ? <LoadingSpinner size="sm" /> : <Check className="h-4 w-4" />}
                          </button>
                          <button onClick={cancelEdit} className="rounded p-1 text-muted-foreground hover:bg-accent" title="Cancel">
                            <X className="h-4 w-4" />
                          </button>
                        </div>
                      </td>
                    </tr>
                  ) : (
                    <tr key={team.id} className="transition-colors hover:bg-muted/20">
                      <td className="px-4 py-3 font-medium">{team.name}</td>
                      <td className="px-4 py-3 font-mono text-xs text-muted-foreground">{team.slug}</td>
                      <td className="px-4 py-3 text-right">
                        <button
                          onClick={() => startEdit(team)}
                          className="rounded p-1.5 text-muted-foreground hover:bg-accent hover:text-foreground"
                          title="Edit"
                        >
                          <Pencil className="h-3.5 w-3.5" />
                        </button>
                      </td>
                    </tr>
                  )
                )}

                {showNewRow && (
                  <tr className="bg-accent/30">
                    <td className="px-4 py-2">
                      <input
                        ref={nameRef}
                        placeholder="Team name"
                        value={newDraft.name}
                        onChange={(e) => handleNewName(e.target.value)}
                        className={inputClass("py-1.5")}
                        onKeyDown={(e) => { if (e.key === "Enter") saveNew(); if (e.key === "Escape") { setShowNewRow(false); setRowError(null); } }}
                      />
                    </td>
                    <td className="px-4 py-2">
                      <input
                        placeholder="team-slug"
                        value={newDraft.slug}
                        onChange={(e) => setNewDraft({ ...newDraft, slug: e.target.value })}
                        className={inputClass("py-1.5 font-mono text-xs")}
                        onKeyDown={(e) => { if (e.key === "Enter") saveNew(); if (e.key === "Escape") { setShowNewRow(false); setRowError(null); } }}
                      />
                    </td>
                    <td className="px-4 py-2 text-right">
                      <div className="flex items-center justify-end gap-1">
                        <button
                          onClick={saveNew}
                          disabled={createMutation.isPending}
                          className="rounded p-1 text-green-600 hover:bg-green-500/10 disabled:opacity-50"
                          title="Create"
                        >
                          {createMutation.isPending ? <LoadingSpinner size="sm" /> : <Check className="h-4 w-4" />}
                        </button>
                        <button onClick={() => { setShowNewRow(false); setRowError(null); }} className="rounded p-1 text-muted-foreground hover:bg-accent" title="Cancel">
                          <X className="h-4 w-4" />
                        </button>
                      </div>
                    </td>
                  </tr>
                )}

                {data?.teams.length === 0 && !showNewRow && (
                  <tr>
                    <td colSpan={3} className="px-4 py-8 text-center text-sm text-muted-foreground">
                      No teams yet. Add your first team below.
                    </td>
                  </tr>
                )}
              </tbody>
            </table>
          </div>

          {rowError && <div className="mt-2"><ErrorBanner message={rowError} /></div>}

          <div className="mt-3">
            {!showNewRow && (
              <GhostButton onClick={openNewRow}>
                <Plus className="h-4 w-4" />
                Add team
              </GhostButton>
            )}
          </div>

          <p className="mt-4 text-xs text-muted-foreground">
            During backfill, all repositories in your GitHub org are ingested and PRs are tagged to whichever team you select. Run a separate backfill per team to assign repos to the correct team.
          </p>
        </>
      )}
    </SectionCard>
  );
}

// ── Section 3: GitHub Backfill ────────────────────────────────────────────────

/** Parse "myorg/repo-name:1234" or "myorg/repo-name:done" → repo name only */
function parseCheckpointRepo(checkpoint: string | null): string | null {
  if (!checkpoint) return null;
  const colon = checkpoint.lastIndexOf(":");
  return colon > 0 ? checkpoint.slice(0, colon) : checkpoint;
}

function elapsedSince(isoString: string | null): string {
  if (!isoString) return "";
  const ms = Date.now() - new Date(isoString).getTime();
  const s = Math.floor(ms / 1000);
  if (s < 60) return `${s}s`;
  const m = Math.floor(s / 60);
  if (m < 60) return `${m}m ${s % 60}s`;
  return `${Math.floor(m / 60)}h ${m % 60}m`;
}

function JobCard({ job }: { job: BackfillJob }) {
  const isPending   = job.status === "pending";
  const isRunning   = job.status === "running";
  const isCompleted = job.status === "completed";
  const isFailed    = job.status === "failed";

  const reposDone  = job.records_processed;           // repos completed
  const reposTotal = job.records_total ?? 0;           // total repos in org
  const pct        = reposTotal > 0 ? Math.round((reposDone / reposTotal) * 100) : 0;
  const currentRepo = isRunning ? parseCheckpointRepo(job.last_checkpoint) : null;

  const pendingTooLong =
    isPending &&
    job.created_at &&
    Date.now() - new Date(job.created_at).getTime() > 30_000;

  return (
    <div className={cn(
      "rounded-lg border p-4 transition-all",
      isRunning   && "border-blue-300 bg-blue-50/50 dark:border-blue-800/50 dark:bg-blue-950/20",
      isPending   && "border-border bg-muted/30",
      isCompleted && "border-green-200 bg-green-50/30 dark:border-green-900/40 dark:bg-green-950/10",
      isFailed    && "border-destructive/30 bg-destructive/5",
    )}>
      {/* Header row */}
      <div className="flex items-start justify-between gap-3">
        <div className="flex items-center gap-2">
          {isPending && <LoadingSpinner size="sm" />}
          {isRunning && <LoadingSpinner size="sm" />}
          {isCompleted && (
            <svg className="h-4 w-4 text-green-600 dark:text-green-400" viewBox="0 0 20 20" fill="currentColor">
              <path fillRule="evenodd" d="M16.704 4.153a.75.75 0 01.143 1.052l-8 10.5a.75.75 0 01-1.127.075l-4.5-4.5a.75.75 0 011.06-1.06l3.894 3.893 7.48-9.817a.75.75 0 011.05-.143z" clipRule="evenodd" />
            </svg>
          )}
          {isFailed && (
            <XCircle className="h-4 w-4 text-destructive" />
          )}
          <span className={cn(
            "text-sm font-semibold",
            isPending   && "text-muted-foreground",
            isRunning   && "text-blue-700 dark:text-blue-300",
            isCompleted && "text-green-700 dark:text-green-300",
            isFailed    && "text-destructive",
          )}>
            {isPending   && "Queued"}
            {isRunning   && "Importing"}
            {isCompleted && "Completed"}
            {isFailed    && "Failed"}
          </span>
          {isRunning && (
            <span className="rounded-full bg-blue-500/10 px-1.5 py-0.5 text-[10px] font-medium text-blue-600 dark:text-blue-400">
              LIVE
            </span>
          )}
        </div>
        <span className="shrink-0 text-xs text-muted-foreground">
          {isRunning   && job.started_at   && `Running for ${elapsedSince(job.started_at)}`}
          {isPending   && job.created_at   && `Queued ${formatRelative(job.created_at)}`}
          {isCompleted && job.completed_at && `Finished ${formatRelative(job.completed_at)}`}
          {isFailed    && job.started_at   && `Failed ${formatRelative(job.started_at)}`}
        </span>
      </div>

      {/* Date range */}
      <p className="mt-1 text-xs text-muted-foreground tabular-nums">
        {job.date_from} → {job.date_to}
      </p>

      {/* Progress section — only when running or completed with data */}
      {(isRunning || (isCompleted && reposTotal > 0)) && (
        <div className="mt-3 space-y-1.5">
          {/* Current repo label */}
          {currentRepo && (
            <p className="truncate text-xs text-muted-foreground">
              Processing: <span className="font-medium text-foreground">{currentRepo}</span>
            </p>
          )}

          {/* Bar */}
          {reposTotal > 0 ? (
            <div>
              <div className="mb-1 flex justify-between text-xs text-muted-foreground">
                <span>{reposDone.toLocaleString()} of {reposTotal.toLocaleString()} repos</span>
                <span>{pct}%</span>
              </div>
              <div className="h-2 w-full overflow-hidden rounded-full bg-muted">
                <div
                  className={cn(
                    "h-full rounded-full transition-all duration-700",
                    isCompleted ? "bg-green-500" : "bg-blue-500"
                  )}
                  style={{ width: `${pct}%` }}
                />
              </div>
            </div>
          ) : isRunning ? (
            /* Indeterminate pulse while total not yet known */
            <div className="h-2 w-full overflow-hidden rounded-full bg-muted">
              <div className="h-full w-1/3 animate-pulse rounded-full bg-blue-400" />
            </div>
          ) : null}
        </div>
      )}

      {/* Pending too long hint */}
      {pendingTooLong && (
        <p className="mt-2 text-xs text-amber-600 dark:text-amber-400">
          Still queued — make sure the Celery worker container is running.
        </p>
      )}

      {/* Error message */}
      {isFailed && job.error_message && (
        <p className="mt-2 rounded bg-destructive/10 px-2 py-1.5 text-xs text-destructive">
          {job.error_message}
        </p>
      )}

      {/* Completed summary */}
      {isCompleted && (
        <p className="mt-2 text-xs text-muted-foreground">
          {reposTotal > 0 ? `${reposTotal.toLocaleString()} repos processed` : "Completed"}
          {job.started_at && job.completed_at && (() => {
            const dur = Math.round(
              (new Date(job.completed_at).getTime() - new Date(job.started_at).getTime()) / 1000
            );
            const m = Math.floor(dur / 60);
            const s = dur % 60;
            return ` in ${m > 0 ? `${m}m ` : ""}${s}s`;
          })()}
        </p>
      )}
    </div>
  );
}

function jobsHaveActiveWork(jobs: BackfillJob[]): boolean {
  return jobs.some((j) => j.status === "pending" || j.status === "running");
}

function BackfillSection() {
  const qc = useQueryClient();
  const [selectedTeamId, setSelectedTeamId] = useState<string>("");
  const [fromDate, setFromDate] = useState(() => {
    const d = new Date();
    d.setFullYear(d.getFullYear() - 1);
    return d.toISOString().slice(0, 10);
  });
  const [toDate, setToDate] = useState(() => new Date().toISOString().slice(0, 10));
  const [error, setError] = useState<string | null>(null);

  const { data: teamsData } = useQuery<{ teams: AdminTeam[] }>({
    queryKey: ["admin", "teams"],
    queryFn: async () => {
      const { data } = await apiClient.get<{ teams: AdminTeam[] }>("/admin/teams");
      return data;
    },
  });

  const { data: ghStatus } = useQuery<GitHubStatus>({
    queryKey: ["admin", "github-status"],
    queryFn: async () => {
      const { data } = await apiClient.get<GitHubStatus>("/admin/integrations/github/status");
      return data;
    },
  });

  // Jobs come from the DB — survive tab switches and page refresh.
  // refetchInterval kicks in automatically while any job is still active.
  const { data: jobsData } = useQuery<{ jobs: BackfillJob[]; total: number }>({
    queryKey: ["admin", "backfill-jobs"],
    queryFn: async () => {
      const { data } = await apiClient.get<{ jobs: BackfillJob[]; total: number }>(
        "/admin/integrations/backfill"
      );
      return data;
    },
    refetchInterval: (query) => {
      const jobs = query.state.data?.jobs ?? [];
      return jobsHaveActiveWork(jobs) ? 4000 : false;
    },
  });

  const jobs = jobsData?.jobs ?? [];
  const hasActiveJobs = jobsHaveActiveWork(jobs);

  const triggerMutation = useMutation({
    mutationFn: async () => {
      const { data } = await apiClient.post<BackfillJob>("/admin/integrations/github/backfill", {
        from_date: fromDate,
        to_date: toDate,
        team_id: selectedTeamId || null,
      });
      return data;
    },
    onSuccess: () => {
      setError(null);
      qc.invalidateQueries({ queryKey: ["admin", "backfill-jobs"] });
    },
    onError: (err: unknown) => {
      setError(extractErrorMessage(err) ?? "Failed to start backfill.");
    },
  });

  function handleTrigger(e: React.FormEvent) {
    e.preventDefault();
    setError(null);
    triggerMutation.mutate();
  }

  const isConnected = ghStatus?.connected ?? false;

  return (
    <SectionCard
      title="GitHub Backfill"
      subtitle="Pull historical PR, commit, and release data from GitHub into the platform."
    >
      {!isConnected && (
        <div className="mb-5 rounded-md border border-amber-200 bg-amber-50 px-4 py-3 text-sm text-amber-800 dark:border-amber-800/40 dark:bg-amber-900/20 dark:text-amber-300">
          GitHub is not connected. Complete Step 1 above before running a backfill.
        </div>
      )}

      <form onSubmit={handleTrigger} className={cn("space-y-4", !isConnected && "pointer-events-none opacity-50")}>
        <div className="grid gap-4 sm:grid-cols-3">
          <div>
            <label className="mb-1.5 block text-sm font-medium">Team (optional)</label>
            <div className="relative">
              <select
                value={selectedTeamId}
                onChange={(e) => setSelectedTeamId(e.target.value)}
                className={cn(inputClass(), "appearance-none pr-8")}
              >
                <option value="">All teams / unassigned</option>
                {teamsData?.teams.map((t) => (
                  <option key={t.id} value={t.id}>{t.name}</option>
                ))}
              </select>
              <ChevronDown className="pointer-events-none absolute right-2.5 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground" />
            </div>
            <p className="mt-1 text-xs text-muted-foreground">PRs will be attributed to this team.</p>
          </div>

          <div>
            <label className="mb-1.5 block text-sm font-medium">From date</label>
            <input
              type="date"
              value={fromDate}
              onChange={(e) => setFromDate(e.target.value)}
              className={inputClass()}
            />
          </div>

          <div>
            <label className="mb-1.5 block text-sm font-medium">To date</label>
            <input
              type="date"
              value={toDate}
              onChange={(e) => setToDate(e.target.value)}
              className={inputClass()}
            />
          </div>
        </div>

        {error && <ErrorBanner message={error} />}

        <PrimaryButton type="submit" loading={triggerMutation.isPending} disabled={!isConnected}>
          <RefreshCw className="h-4 w-4" />
          Start backfill
        </PrimaryButton>
      </form>

      {/* Job list — reads from DB, persists across tab switches */}
      {jobs.length > 0 && (
        <div className="mt-6 space-y-3">
          <div className="flex items-center gap-2">
            <h3 className="text-sm font-medium">Backfill jobs</h3>
            {hasActiveJobs && (
              <span className="inline-flex items-center gap-1 rounded-full bg-blue-500/10 px-2 py-0.5 text-xs text-blue-600 dark:text-blue-400">
                <LoadingSpinner size="sm" />
                Polling every 4s
              </span>
            )}
          </div>
          {jobs.map((job) => <JobCard key={job.id} job={job} />)}
        </div>
      )}
    </SectionCard>
  );
}

// ── Root admin page ───────────────────────────────────────────────────────────

export function Admin() {
  const user = useAuthStore((s) => s.user);

  if (user?.role !== "admin") {
    return (
      <div className="flex h-64 flex-col items-center justify-center gap-2">
        <p className="text-lg font-medium">Access denied</p>
        <p className="text-sm text-muted-foreground">This page is restricted to admins.</p>
      </div>
    );
  }

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold">Admin</h1>
          <p className="mt-0.5 text-sm text-muted-foreground">
            Configure integrations and import data.
          </p>
        </div>
      </div>

      <GitHubConnectSection />
      <TeamManagementSection />
      <BackfillSection />
    </div>
  );
}

// ── Utilities ─────────────────────────────────────────────────────────────────

function extractErrorMessage(err: unknown): string | null {
  if (!err || typeof err !== "object") return null;
  const e = err as { response?: { data?: { detail?: string | { error?: { message?: string } } } } };
  const detail = e.response?.data?.detail;
  if (typeof detail === "string") return detail;
  if (detail && typeof detail === "object" && "error" in detail) {
    return detail.error?.message ?? null;
  }
  return null;
}

function formatRelative(iso: string): string {
  const diff = Date.now() - new Date(iso).getTime();
  const mins = Math.floor(diff / 60_000);
  if (mins < 1) return "just now";
  if (mins < 60) return `${mins}m ago`;
  const hrs = Math.floor(mins / 60);
  if (hrs < 24) return `${hrs}h ago`;
  return `${Math.floor(hrs / 24)}d ago`;
}
