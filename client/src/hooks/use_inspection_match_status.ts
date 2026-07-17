import { useEffect, useState } from "react";

import { resolveFetchUrl } from "@/lib/api/http";

export type MatchStatus = "matched" | "needs_review" | "no_match";

export interface MatchStatusResponse {
  inspection_id: string;
  match_status: MatchStatus;
  bbox: { x: number; y: number; width: number; height: number } | null;
}

export function buildInspectionMatchStatusUrl(inspectionId: string): string {
  return `/api/inspections/${inspectionId}/match-status`;
}

export async function fetchInspectionMatchStatus(
  inspectionId: string,
): Promise<MatchStatusResponse> {
  const response = await fetch(resolveFetchUrl(buildInspectionMatchStatusUrl(inspectionId)), {
    credentials: "include",
  });

  if (!response.ok) {
    throw new Error("Failed to fetch inspection match status");
  }

  return response.json() as Promise<MatchStatusResponse>;
}

export function useInspectionMatchStatus(inspectionId: string) {
  const [data, setData] = useState<MatchStatusResponse | null>(null);

  useEffect(() => {
    if (!inspectionId) return;

    let cancelled = false;

    fetchInspectionMatchStatus(inspectionId)
      .then((result) => {
        if (!cancelled) {
          setData(result);
        }
      })
      .catch(() => {
        if (!cancelled) {
          setData({
            inspection_id: inspectionId,
            match_status: "needs_review",
            bbox: null,
          });
        }
      });

    return () => {
      cancelled = true;
    };
  }, [inspectionId]);

  return data;
}
