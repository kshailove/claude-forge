import { useQuery } from "@tanstack/react-query";
import apiClient from "@/lib/apiClient";
import type {
  IncidentsByServiceResponse,
  IncidentsListResponse,
  IncidentsSummaryResponse,
  IncidentsTimelineResponse,
  OncallLoadResponse,
} from "@/lib/types";

export interface IncidentsListParams {
  window_days?: number;
  severity?: string;
  team_id?: string;
  page?: number;
  page_size?: number;
}

export function useIncidentsList(params: IncidentsListParams = {}) {
  const {
    window_days = 30,
    severity,
    team_id,
    page = 1,
    page_size = 50,
  } = params;

  return useQuery<IncidentsListResponse>({
    queryKey: ["incidents", "list", window_days, severity, team_id, page, page_size],
    queryFn: async () => {
      const searchParams = new URLSearchParams();
      searchParams.set("window_days", String(window_days));
      searchParams.set("page", String(page));
      searchParams.set("page_size", String(page_size));
      if (severity) searchParams.set("severity", severity);
      if (team_id) searchParams.set("team_id", team_id);

      const { data } = await apiClient.get<IncidentsListResponse>(
        `/incidents?${searchParams.toString()}`
      );
      return data;
    },
    staleTime: 2 * 60 * 1000,
  });
}

export function useIncidentsSummary(windowDays: number = 30, teamId?: string) {
  return useQuery<IncidentsSummaryResponse>({
    queryKey: ["incidents", "summary", windowDays, teamId],
    queryFn: async () => {
      const searchParams = new URLSearchParams({ window_days: String(windowDays) });
      if (teamId) searchParams.set("team_id", teamId);
      const { data } = await apiClient.get<IncidentsSummaryResponse>(
        `/incidents/summary?${searchParams.toString()}`
      );
      return data;
    },
    staleTime: 2 * 60 * 1000,
  });
}

export function useOncallLoad(windowDays: number = 30, teamId?: string) {
  return useQuery<OncallLoadResponse>({
    queryKey: ["incidents", "oncall-load", windowDays, teamId],
    queryFn: async () => {
      const searchParams = new URLSearchParams({ window_days: String(windowDays) });
      if (teamId) searchParams.set("team_id", teamId);
      const { data } = await apiClient.get<OncallLoadResponse>(
        `/incidents/oncall-load?${searchParams.toString()}`
      );
      return data;
    },
    staleTime: 2 * 60 * 1000,
  });
}

export function useIncidentsByService(windowDays: number = 30, teamId?: string) {
  return useQuery<IncidentsByServiceResponse>({
    queryKey: ["incidents", "by-service", windowDays, teamId],
    queryFn: async () => {
      const searchParams = new URLSearchParams({ window_days: String(windowDays) });
      if (teamId) searchParams.set("team_id", teamId);
      const { data } = await apiClient.get<IncidentsByServiceResponse>(
        `/incidents/by-service?${searchParams.toString()}`
      );
      return data;
    },
    staleTime: 2 * 60 * 1000,
  });
}

export function useIncidentsTimeline(windowDays: number = 30, teamId?: string) {
  return useQuery<IncidentsTimelineResponse>({
    queryKey: ["incidents", "timeline", windowDays, teamId],
    queryFn: async () => {
      const searchParams = new URLSearchParams({ window_days: String(windowDays) });
      if (teamId) searchParams.set("team_id", teamId);
      const { data } = await apiClient.get<IncidentsTimelineResponse>(
        `/incidents/timeline?${searchParams.toString()}`
      );
      return data;
    },
    staleTime: 2 * 60 * 1000,
  });
}
