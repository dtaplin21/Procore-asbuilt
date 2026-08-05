export type DrawingIndexStatus = "pending" | "processing" | "ready" | "failed";

export interface DrawingIndexStatusResponse {
  status: DrawingIndexStatus;
  stats: {
    pages?: number;
    regions?: number;
    text_elements?: number;
    scale_found?: boolean;
  } | null;
  scale: {
    raw_text?: string;
    real_feet_per_paper_inch?: number;
  } | null;
  error: string | null;
  indexed_at: string | null;
}

export interface DrawingReindexResponse {
  job_id: number;
  index_status: string;
}

/** Human-readable summary for the Objects drawing header after indexing completes. */
export function formatDrawingIndexSummary(
  data: DrawingIndexStatusResponse | null | undefined,
): string | null {
  if (!data) return null;
  if (data.status === "processing") return null;
  if (data.status === "pending") return null;
  if (data.status === "failed") return null;

  const parts: string[] = [];
  const regions = data.stats?.regions;
  if (typeof regions === "number" && regions >= 0) {
    parts.push(`${regions} region${regions === 1 ? "" : "s"} indexed`);
  }
  const rawScale = data.scale?.raw_text?.trim();
  if (rawScale) {
    parts.push(`Scale ${rawScale}`);
  }
  const pages = data.stats?.pages;
  if (typeof pages === "number" && pages > 0) {
    parts.push(`${pages} page${pages === 1 ? "" : "s"}`);
  }
  return parts.length > 0 ? parts.join(" · ") : null;
}

export function isDrawingIndexInProgress(
  status: DrawingIndexStatus | string | null | undefined,
): boolean {
  return status === "processing" || status === "pending";
}
