import { useQuery } from "@tanstack/react-query";
import apiClient from "@/lib/apiClient";
import type {
  IncidentLoadDetailResponse,
  PRHealthDetailResponse,
  SlackSignalDetailResponse,
  SprintHealthDetailResponse,
  StalePRListResponse,
  TeamDetailResponse,
  TeamMembersResponse,
} from "@/lib/types";

export function useTeamDetail(teamId: string) {
  return useQuery<TeamDetailResponse>({
    queryKey: ["team", teamId],
    queryFn: async () => {
      const { data } = await apiClient.get<TeamDetailResponse>(`/teams/${teamId}`);
      return data;
    },
    enabled: Boolean(teamId),
    staleTime: 2 * 60 * 1000,
  });
}

export function usePRHealth(teamId: string) {
  return useQuery<PRHealthDetailResponse>({
    queryKey: ["team", teamId, "pr-health"],
    queryFn: async () => {
      const { data } = await apiClient.get<PRHealthDetailResponse>(
        `/teams/${teamId}/pr-health`
      );
      return data;
    },
    enabled: Boolean(teamId),
    staleTime: 2 * 60 * 1000,
  });
}

export function useStalePRs(teamId: string) {
  return useQuery<StalePRListResponse>({
    queryKey: ["team", teamId, "stale-prs"],
    queryFn: async () => {
      const { data } = await apiClient.get<StalePRListResponse>(
        `/teams/${teamId}/pr-health/stale-prs`
      );
      return data;
    },
    enabled: Boolean(teamId),
    staleTime: 5 * 60 * 1000,
  });
}

export function useSprintHealth(teamId: string) {
  return useQuery<SprintHealthDetailResponse>({
    queryKey: ["team", teamId, "sprint-health"],
    queryFn: async () => {
      const { data } = await apiClient.get<SprintHealthDetailResponse>(
        `/teams/${teamId}/sprint-health`
      );
      return data;
    },
    enabled: Boolean(teamId),
    staleTime: 2 * 60 * 1000,
  });
}

export function useIncidentLoad(teamId: string) {
  return useQuery<IncidentLoadDetailResponse>({
    queryKey: ["team", teamId, "incident-load"],
    queryFn: async () => {
      const { data } = await apiClient.get<IncidentLoadDetailResponse>(
        `/teams/${teamId}/incident-load`
      );
      return data;
    },
    enabled: Boolean(teamId),
    staleTime: 2 * 60 * 1000,
  });
}

export function useSlackSignal(teamId: string) {
  return useQuery<SlackSignalDetailResponse>({
    queryKey: ["team", teamId, "slack-signal"],
    queryFn: async () => {
      const { data } = await apiClient.get<SlackSignalDetailResponse>(
        `/teams/${teamId}/slack-signal`
      );
      return data;
    },
    enabled: Boolean(teamId),
    staleTime: 5 * 60 * 1000,
  });
}

export function useTeamMembers(teamId: string) {
  return useQuery<TeamMembersResponse>({
    queryKey: ["team", teamId, "members"],
    queryFn: async () => {
      const { data } = await apiClient.get<TeamMembersResponse>(
        `/teams/${teamId}/members`
      );
      return data;
    },
    enabled: Boolean(teamId),
    staleTime: 5 * 60 * 1000,
  });
}
