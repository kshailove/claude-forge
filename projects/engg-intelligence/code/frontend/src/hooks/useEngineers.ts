import { useQuery } from "@tanstack/react-query";
import apiClient from "@/lib/apiClient";
import type { EngineerDetailResponse, EngineersListResponse } from "@/lib/types";

export function useEngineersList() {
  return useQuery<EngineersListResponse>({
    queryKey: ["engineers"],
    queryFn: async () => {
      const { data } = await apiClient.get<EngineersListResponse>("/engineers");
      return data;
    },
    staleTime: 2 * 60 * 1000,
  });
}

export function useEngineerDetail(userId: string) {
  return useQuery<EngineerDetailResponse>({
    queryKey: ["engineer", userId],
    queryFn: async () => {
      const { data } = await apiClient.get<EngineerDetailResponse>(
        `/engineers/${userId}`
      );
      return data;
    },
    enabled: Boolean(userId),
    staleTime: 2 * 60 * 1000,
  });
}
