import { useOverview } from "@/hooks/useOverview";
import { useAuthStore } from "@/stores/authStore";
import { TeamHealthCard } from "@/components/TeamHealthCard";
import { PageLoader } from "@/components/LoadingSpinner";

export function Overview() {
  const { data, isLoading, error } = useOverview();
  const user = useAuthStore((s) => s.user);

  if (isLoading) return <PageLoader />;

  if (error) {
    return (
      <div className="flex h-64 items-center justify-center">
        <p className="text-sm text-muted-foreground">
          Failed to load overview. Please try again.
        </p>
      </div>
    );
  }

  if (!data || data.teams.length === 0) {
    return (
      <div className="flex h-64 flex-col items-center justify-center gap-2">
        <p className="text-lg font-medium">No teams found</p>
        <p className="text-sm text-muted-foreground">
          You have not been assigned to a team yet.
        </p>
      </div>
    );
  }

  const isEM = user?.role === "em";

  if (isEM && data.teams.length === 1) {
    // EM single-team view — large card
    return (
      <div className="mx-auto max-w-2xl">
        <TeamHealthCard card={data.teams[0]} large />
      </div>
    );
  }

  // Director/Admin grid view
  return (
    <div>
      <div className="mb-6 flex items-center justify-between">
        <h1 className="text-2xl font-bold">Organisation Overview</h1>
        <p className="text-sm text-muted-foreground">
          {data.total} team{data.total !== 1 ? "s" : ""}
        </p>
      </div>
      <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 xl:grid-cols-3">
        {data.teams.map((card) => (
          <TeamHealthCard key={card.team_id} card={card} />
        ))}
      </div>
    </div>
  );
}
