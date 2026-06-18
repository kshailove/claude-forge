import { useQuery } from "@tanstack/react-query";
import apiClient from "@/lib/apiClient";
import type { TeamsListResponse } from "@/lib/types";

export function useTeams() {
  return useQuery<TeamsListResponse>({
    queryKey: ["teams"],
    queryFn: async () => {
      const { data } = await apiClient.get<TeamsListResponse>("/teams");
      return data;
    },
    staleTime: 2 * 60 * 1000,
  });
}
