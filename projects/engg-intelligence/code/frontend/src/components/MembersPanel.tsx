import { Clock, GitPullRequest, AlertTriangle } from "lucide-react";
import { PageLoader } from "./LoadingSpinner";
import { useTeamMembers } from "@/hooks/useTeamDetail";

interface MembersPanelProps {
  teamId: string;
}

const ROLE_LABELS: Record<string, string> = {
  engineer: "Engineer",
  em: "Engineering Manager",
  director: "Director",
  admin: "Admin",
};

export function MembersPanel({ teamId }: MembersPanelProps) {
  const { data, isLoading, error } = useTeamMembers(teamId);

  if (isLoading) return <PageLoader />;
  if (error || !data)
    return (
      <p className="py-8 text-center text-sm text-muted-foreground">
        Failed to load team members.
      </p>
    );

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <h3 className="font-medium">
          Team Members ({data.total})
        </h3>
      </div>

      <div className="overflow-x-auto rounded-lg border border-border">
        <table className="w-full text-sm">
          <thead className="bg-muted/50">
            <tr>
              <th className="px-4 py-3 text-left font-medium text-muted-foreground">
                Member
              </th>
              <th className="px-4 py-3 text-left font-medium text-muted-foreground">
                Role
              </th>
              <th className="px-4 py-3 text-center font-medium text-muted-foreground">
                <span className="flex items-center justify-center gap-1">
                  <GitPullRequest className="h-3.5 w-3.5" />
                  Open PRs
                </span>
              </th>
              <th className="px-4 py-3 text-center font-medium text-muted-foreground">
                <span className="flex items-center justify-center gap-1">
                  <Clock className="h-3.5 w-3.5" />
                  On-call (7d)
                </span>
              </th>
              <th className="px-4 py-3 text-center font-medium text-muted-foreground">
                <span className="flex items-center justify-center gap-1">
                  <AlertTriangle className="h-3.5 w-3.5" />
                  Active Incidents
                </span>
              </th>
            </tr>
          </thead>
          <tbody className="divide-y divide-border">
            {data.members.map((member) => (
              <tr key={member.user_id} className="hover:bg-muted/30">
                <td className="px-4 py-3">
                  <div>
                    <p className="font-medium">{member.username}</p>
                    <p className="text-xs text-muted-foreground">
                      {member.email}
                    </p>
                  </div>
                </td>
                <td className="px-4 py-3 text-muted-foreground">
                  {ROLE_LABELS[member.role] ?? member.role}
                </td>
                <td className="px-4 py-3 text-center tabular-nums">
                  <span
                    className={
                      member.open_pr_count > 3
                        ? "font-semibold text-amber-600"
                        : ""
                    }
                  >
                    {member.open_pr_count}
                  </span>
                </td>
                <td className="px-4 py-3 text-center tabular-nums">
                  {member.on_call_hours_7d.toFixed(1)}h
                </td>
                <td className="px-4 py-3 text-center tabular-nums">
                  <span
                    className={
                      member.active_incident_count > 0
                        ? "font-semibold text-red-600"
                        : ""
                    }
                  >
                    {member.active_incident_count}
                  </span>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
