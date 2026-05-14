import type { DrawingDiff, DrawingDiffRegion, ReviewBadgeTone } from "@/types/drawing_workspace";

export type OverlayInspectionTone = ReviewBadgeTone | "neutral";

const OVERLAY_PALETTE: Record<
  OverlayInspectionTone,
  { stroke: string; fill: string; strokeMuted: string; fillMuted: string }
> = {
  changed: {
    stroke: "#d97706",
    fill: "rgba(217, 119, 6, 0.14)",
    strokeMuted: "#b45309",
    fillMuted: "rgba(180, 83, 9, 0.18)",
  },
  passed: {
    stroke: "#16a34a",
    fill: "rgba(22, 163, 74, 0.12)",
    strokeMuted: "#15803d",
    fillMuted: "rgba(21, 128, 61, 0.16)",
  },
  failed: {
    stroke: "#dc2626",
    fill: "rgba(220, 38, 38, 0.14)",
    strokeMuted: "#b91c1c",
    fillMuted: "rgba(185, 28, 28, 0.18)",
  },
  neutral: {
    stroke: "#d97706",
    fill: "rgba(217, 119, 6, 0.12)",
    strokeMuted: "#b45309",
    fillMuted: "rgba(180, 83, 9, 0.15)",
  },
};

export function overlayColorsForTone(tone: OverlayInspectionTone, selected: boolean) {
  const p = OVERLAY_PALETTE[tone];
  const strokeWidth = selected ? 3 : 2;
  return {
    stroke: selected ? p.strokeMuted : p.stroke,
    fill: selected ? p.fillMuted : p.fill,
    strokeWidth,
  };
}

export function regionOverlayTone(
  region: DrawingDiffRegion,
  diff: DrawingDiff,
  showInspectionStatuses: boolean
): OverlayInspectionTone {
  if (!showInspectionStatuses) {
    return "neutral";
  }
  const badge = region.reviewBadge ?? diff.reviewBadge ?? null;
  if (badge === "passed" || badge === "failed" || badge === "changed") {
    return badge;
  }
  return "changed";
}

export function includeRegionWhenChangesOnly(
  region: DrawingDiffRegion,
  diff: DrawingDiff,
  showChangesOnly: boolean
): boolean {
  if (!showChangesOnly) {
    return true;
  }
  const badge = region.reviewBadge ?? diff.reviewBadge;
  return badge == null || badge === "changed";
}
