import { useNavigate } from "react-router-dom";
import { useTeams } from "@/hooks/useTeams";
import { useAuthStore } from "@/stores/authStore";
import { RAGBadge } from "@/components/RAGBadge";
import { PageLoader } from "@/components/LoadingSpinner";

export function Teams() {
  const navigate = useNavigate();
  const { data, isLoading, error } = useTeams();
  const user = useAuthStore((s) => s.user);

  if (isLoading) return <PageLoader />;

  if (error) {
    return (
      <div className="flex h-64 items-center justify-center">
        <p className="text-sm text-muted-foreground">
          Failed to load teams. Please try again.
        </p>
      </div>
    );
  }

  if (!data || data.teams.length === 0) {
    return (
      <div className="flex h-64 flex-col items-center justify-center gap-2">
        <p className="text-lg font-medium">No teams found</p>
        <p className="text-sm text-muted-foreground">
          You do not have access to any teams.
        </p>
      </div>
    );
  }

  // EMs only see their own team — redirect to detail directly
  const isEM = user?.role === "em";
  if (isEM && data.teams.length === 1) {
    navigate(`/teams/${data.teams[0].team_id}`, { replace: true });
    return null;
  }

  return (
    <div>
      <div className="mb-6 flex items-center justify-between">
        <h1 className="text-2xl font-bold">Teams</h1>
        <p className="text-sm text-muted-foreground">
          {data.total} team{data.total !== 1 ? "s" : ""}
        </p>
      </div>

      <div className="overflow-hidden rounded-xl border border-border bg-card shadow-sm">
        <table className="w-full text-sm">
          <thead className="border-b border-border bg-muted/40">
            <tr>
              <th className="px-6 py-4 text-left font-medium text-muted-foreground">
                Team
              </th>
              <th className="px-6 py-4 text-left font-medium text-muted-foreground">
                Engineering Manager
              </th>
              <th className="px-6 py-4 text-center font-medium text-muted-foreground">
                Members
              </th>
              <th className="px-6 py-4 text-center font-medium text-muted-foreground">
                Health Score
              </th>
              <th className="px-6 py-4 text-center font-medium text-muted-foreground">
                Status
              </th>
            </tr>
          </thead>
          <tbody className="divide-y divide-border">
            {data.teams.map((team) => (
              <tr
                key={team.team_id}
                className="cursor-pointer transition-colors hover:bg-muted/30"
                onClick={() => navigate(`/teams/${team.team_id}`)}
              >
                <td className="px-6 py-4">
                  <div>
                    <p className="font-medium">{team.team_name}</p>
                    <p className="text-xs text-muted-foreground">
                      {team.slug}
                    </p>
                  </div>
                </td>
                <td className="px-6 py-4 text-muted-foreground">
                  {team.em_username ?? "—"}
                </td>
                <td className="px-6 py-4 text-center tabular-nums">
                  {team.member_count}
                </td>
                <td className="px-6 py-4 text-center tabular-nums font-bold">
                  {team.composite_score != null
                    ? team.composite_score.toFixed(0)
                    : "—"}
                </td>
                <td className="px-6 py-4">
                  <div className="flex justify-center">
                    <RAGBadge rag={team.rag} showLabel size="sm" />
                  </div>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
