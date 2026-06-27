/**
 * Formats hover-tooltip fields for a region, per spec §4.
 *
 * Inspected region:
 *   Location, Inspection, Date, Inspection #, Status (full vocab string)
 *
 * Admin mode, uninspected region (faint outline only):
 *   Location, "Not yet inspected"
 *
 * Status always comes from inspectionStatusDisplay — never derived or
 * simplified. When absent, this module omits statusLine rather than
 * showing "Unknown" (spec §2 allows either; omitting avoids implying a
 * definite-but-unrecognized status).
 */

import type {
  RegionInspectionSummaryEntry,
  RegionViewerState,
} from "@/lib/drawing-regions/types";

export interface RegionTooltipContent {
  locationLine: string;
  inspectionLine: string;
  dateLine: string | null;
  inspectionNumberLine: string | null;
  statusLine: string | null;
}

function formatDate(isoDate: string): string {
  const date = new Date(`${isoDate}T00:00:00`);
  if (Number.isNaN(date.getTime())) {
    return isoDate;
  }
  return date.toLocaleDateString("en-US", {
    month: "short",
    day: "numeric",
    year: "numeric",
  });
}

function resolveLocation(entry: RegionInspectionSummaryEntry): string {
  const tag = entry.locationTags[0]?.trim();
  if (tag) return tag;
  const label = entry.label?.trim();
  if (label) return label;
  return `Region ${entry.regionId}`;
}

export function buildRegionTooltipContent(
  entry: RegionInspectionSummaryEntry,
  state: RegionViewerState,
): RegionTooltipContent {
  const location = resolveLocation(entry);

  if (state !== "inspected") {
    return {
      locationLine: location,
      inspectionLine: "Not yet inspected",
      dateLine: null,
      inspectionNumberLine: null,
      statusLine: null,
    };
  }

  const inspectionType =
    entry.inspectionTypeTags[0] ?? entry.inspectionType ?? "Inspection";
  const dateLine = entry.inspectionDate ? formatDate(entry.inspectionDate) : null;

  let inspectionNumberLine: string | null = null;
  if (entry.latestInspectionRunId != null) {
    inspectionNumberLine = `Run ${entry.latestInspectionRunId}`;
    if (entry.procoreInspectionId) {
      inspectionNumberLine += ` (Procore ${entry.procoreInspectionId})`;
    }
  }

  return {
    locationLine: location,
    inspectionLine: inspectionType,
    dateLine,
    inspectionNumberLine,
    statusLine: entry.inspectionStatusDisplay ?? null,
  };
}
