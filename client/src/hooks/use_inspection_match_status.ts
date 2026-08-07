import { useEffect, useRef } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";

import { resolveFetchUrl } from "@/lib/api/http";
import { invalidateOverlaysForRun } from "@/lib/api/overlays";

export const MATCH_STATUS_POLL_INTERVAL_MS = 2000;
export const MATCH_STATUS_MAX_POLL_ATTEMPTS = 30;

export type MatchStatus = "matched" | "needs_review" | "no_match" | "index_pending";

export interface MatchStatusResponse {
  inspection_id: string;
  match_status: MatchStatus;
  bbox: { x: number; y: number; width: number; height: number } | null;
}

export interface UseInspectionMatchStatusOptions {
  /** Master drawing id — used to refetch overlays when matching completes. */
  drawingId?: string;
  /** Inspection run id — scopes overlay invalidation to the active run. */
  runId?: string | null;
  enabled?: boolean;
  onJobComplete?: () => void;
}

export function isTerminalMatchStatus(status: MatchStatus | undefined): boolean {
  return (
    status === "matched" ||
    status === "needs_review" ||
    status === "no_match"
  );
}

export function buildInspectionMatchStatusUrl(evidenceId: string): string {
  return `/api/inspections/${evidenceId}/match-status`;
}

export function inspectionMatchStatusQueryKey(evidenceId: string) {
  return ["inspection-match-status", evidenceId] as const;
}

export async function fetchInspectionMatchStatus(
  evidenceId: string,
): Promise<MatchStatusResponse> {
  const response = await fetch(resolveFetchUrl(buildInspectionMatchStatusUrl(evidenceId)), {
    credentials: "include",
  });

  if (!response.ok) {
    throw new Error("Failed to fetch inspection match status");
  }

  return response.json() as Promise<MatchStatusResponse>;
}

export function useInspectionMatchStatus(
  evidenceId: string | null | undefined,
  options?: UseInspectionMatchStatusOptions,
) {
  const queryClient = useQueryClient();
  const pollAttemptsRef = useRef(0);
  const sawIndexPendingRef = useRef(false);
  const refreshedOverlaysRef = useRef(false);
  const onJobCompleteRef = useRef(options?.onJobComplete);
  onJobCompleteRef.current = options?.onJobComplete;

  const enabled = Boolean(evidenceId) && (options?.enabled ?? true);

  useEffect(() => {
    pollAttemptsRef.current = 0;
    sawIndexPendingRef.current = false;
    refreshedOverlaysRef.current = false;
  }, [evidenceId]);

  const query = useQuery({
    queryKey: evidenceId
      ? inspectionMatchStatusQueryKey(evidenceId)
      : ["inspection-match-status", "disabled"],
    queryFn: async () => {
      pollAttemptsRef.current += 1;
      return fetchInspectionMatchStatus(evidenceId!);
    },
    enabled,
    retry: false,
    refetchInterval: (activeQuery) => {
      const status = activeQuery.state.data?.match_status;
      if (status === "index_pending") {
        sawIndexPendingRef.current = true;
      }
      if (isTerminalMatchStatus(status)) {
        return false;
      }
      if (pollAttemptsRef.current >= MATCH_STATUS_MAX_POLL_ATTEMPTS) {
        return false;
      }
      return MATCH_STATUS_POLL_INTERVAL_MS;
    },
  });

  useEffect(() => {
    const status = query.data?.match_status;
    if (
      !status ||
      !isTerminalMatchStatus(status) ||
      !sawIndexPendingRef.current ||
      refreshedOverlaysRef.current
    ) {
      return;
    }

    refreshedOverlaysRef.current = true;
    if (options?.drawingId && options?.runId) {
      invalidateOverlaysForRun(queryClient, options.drawingId, options.runId);
    }
    onJobCompleteRef.current?.();
  }, [query.data, options?.drawingId, options?.runId, queryClient]);

  if (query.isError && evidenceId) {
    return {
      inspection_id: evidenceId,
      match_status: "needs_review" as const,
      bbox: null,
    };
  }

  return query.data ?? null;
}
