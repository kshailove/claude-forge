import { useQuery } from "@tanstack/react-query";
import apiClient from "@/lib/apiClient";
import type {
  DigestDetailResponse,
  DigestListResponse,
  DigestPreviewResponse,
} from "@/lib/types";

/**
 * Fetch the list of past digests for the current user.
 */
export function useDigestsList() {
  return useQuery<DigestListResponse>({
    queryKey: ["digests"],
    queryFn: async () => {
      const { data } = await apiClient.get<DigestListResponse>("/digests");
      return data;
    },
    staleTime: 5 * 60 * 1000, // 5 minutes
  });
}

/**
 * Fetch the full rendered HTML for one specific digest.
 */
export function useDigestDetail(digestId: string | null) {
  return useQuery<DigestDetailResponse>({
    queryKey: ["digests", digestId],
    queryFn: async () => {
      const { data } = await apiClient.get<DigestDetailResponse>(
        `/digests/${digestId}`
      );
      return data;
    },
    enabled: Boolean(digestId),
    staleTime: 10 * 60 * 1000, // 10 minutes — digest HTML doesn't change
  });
}

/**
 * Fetch a live preview of next Monday's digest (not stored).
 */
export function useDigestPreview(enabled: boolean) {
  return useQuery<DigestPreviewResponse>({
    queryKey: ["digests", "preview"],
    queryFn: async () => {
      const { data } =
        await apiClient.get<DigestPreviewResponse>("/digests/preview");
      return data;
    },
    enabled,
    staleTime: 2 * 60 * 1000, // 2 minutes
  });
}
