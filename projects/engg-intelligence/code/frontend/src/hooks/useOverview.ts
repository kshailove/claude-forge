import { useQuery } from "@tanstack/react-query";
import apiClient from "@/lib/apiClient";
import type { OverviewResponse } from "@/lib/types";

export function useOverview() {
  return useQuery<OverviewResponse>({
    queryKey: ["overview"],
    queryFn: async () => {
      const { data } = await apiClient.get<OverviewResponse>("/overview");
      return data;
    },
    staleTime: 2 * 60 * 1000, // 2 minutes
  });
}
