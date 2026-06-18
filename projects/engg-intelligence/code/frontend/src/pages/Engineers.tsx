import { useNavigate } from "react-router-dom";
import { User } from "lucide-react";
import { PageLoader } from "@/components/LoadingSpinner";
import { useEngineersList } from "@/hooks/useEngineers";
import { useAuthStore } from "@/stores/authStore";
import { cn } from "@/lib/utils";
import type { EngineerSummary } from "@/lib/types";

const LOAD_STYLES: Record<string, string> = {
  high: "bg-red-100 text-red-700",
  medium: "bg-amber-100 text-amber-700",
  low: "bg-green-100 text-green-700",
};

function LoadBadge({ level }: { level: string }) {
  return (
    <span
      className={cn(
        "inline-flex items-center rounded-full px-2.5 py-0.5 text-xs font-medium capitalize",
        LOAD_STYLES[level] ?? "bg-gray-100 text-gray-700"
      )}
    >
      {level}
    </span>
  );
}

export function Engineers() {
  const navigate = useNavigate();
  const { user } = useAuthStore();
  const { data, isLoading, error } = useEngineersList();

  const isDirectorOrAbove =
    user?.role === "director" || user?.role === "admin";

  if (isLoading) return <PageLoader />;

  if (error || !data) {
    return (
      <p className="py-8 text-center text-sm text-muted-foreground">
        Failed to load engineers.
      </p>
    );
  }

  if (data.engineers.length === 0) {
    return (
      <div className="flex h-64 flex-col items-center justify-center gap-2">
        <User className="h-10 w-10 text-muted-foreground" />
        <p className="text-sm text-muted-foreground">No engineers found.</p>
      </div>
    );
  }

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-3xl font-bold">Engineers</h1>
        <p className="mt-1 text-sm text-muted-foreground">
          {data.total} engineer{data.total !== 1 ? "s" : ""}
          {!isDirectorOrAbove ? " on your team" : " across all teams"}
        </p>
      </div>

      <div className="overflow-x-auto rounded-xl border border-border">
        <table className="w-full text-sm">
          <thead className="bg-muted/50">
            <tr>
              <th className="px-4 py-3 text-left font-medium text-muted-foreground">
                Name
              </th>
              {isDirectorOrAbove && (
                <th className="px-4 py-3 text-left font-medium text-muted-foreground">
                  Team
                </th>
              )}
              <th className="px-4 py-3 text-left font-medium text-muted-foreground">
                Load
              </th>
              <th className="px-4 py-3 text-right font-medium text-muted-foreground">
                PRs (30d)
              </th>
              <th className="px-4 py-3 text-right font-medium text-muted-foreground">
                Tickets (30d)
              </th>
              <th className="px-4 py-3 text-right font-medium text-muted-foreground">
                Pages (30d)
              </th>
            </tr>
          </thead>
          <tbody className="divide-y divide-border">
            {data.engineers.map((eng: EngineerSummary) => (
              <tr
                key={eng.user_id}
                className="cursor-pointer hover:bg-muted/30"
                onClick={() => navigate(`/engineers/${eng.user_id}`)}
              >
                <td className="px-4 py-3">
                  <div className="flex items-center gap-2.5">
                    <div className="flex h-8 w-8 shrink-0 items-center justify-center rounded-full bg-primary/10 text-xs font-semibold uppercase text-primary">
                      {eng.name[0] ?? "?"}
                    </div>
                    <div>
                      <p className="font-medium">{eng.name}</p>
                      <p className="text-xs text-muted-foreground">{eng.email}</p>
                    </div>
                  </div>
                </td>
                {isDirectorOrAbove && (
                  <td className="px-4 py-3 text-muted-foreground">
                    {eng.team_name ?? "—"}
                  </td>
                )}
                <td className="px-4 py-3">
                  <LoadBadge level={eng.composite_load_indicator} />
                </td>
                <td className="px-4 py-3 text-right tabular-nums">
                  <span title={`${eng.pr_merged_30d} merged`}>
                    {eng.pr_authored_30d}
                    <span className="ml-1 text-xs text-muted-foreground">
                      ({eng.pr_merged_30d} merged)
                    </span>
                  </span>
                </td>
                <td className="px-4 py-3 text-right tabular-nums">
                  {eng.tickets_closed_30d}
                </td>
                <td className="px-4 py-3 text-right tabular-nums">
                  {eng.incidents_paged_30d > 0 ? (
                    <span className="font-medium text-red-600">
                      {eng.incidents_paged_30d}
                    </span>
                  ) : (
                    <span className="text-muted-foreground">0</span>
                  )}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
