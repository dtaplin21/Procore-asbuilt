import type { DrawingDiff } from "@/types/drawing_workspace";
import type { ResolvedOverlayRegion, ViewerSize } from "@/lib/drawing-overlays/overlay-types";
import { resolveOverlayRegion } from "@/lib/drawing-overlays/geometry";
import {
  includeRegionWhenChangesOnly,
  regionOverlayTone,
  type OverlayInspectionTone,
} from "@/lib/drawing-overlays/inspection_overlay";
import DiffOverlayShape from "@/components/drawing-workspace/diff_overlay_shape";

type Props = {
  diff: DrawingDiff | null;
  viewerSize: ViewerSize;
  /** When true, only regions that are still "changed" (or not yet reviewed) are drawn. */
  showChangesOnly?: boolean;
  /** When false, all regions use the same highlight (amber); no passed/failed coloring. */
  showInspectionStatuses?: boolean;
};

export default function DrawingOverlayLayer({
  diff,
  viewerSize,
  showChangesOnly = false,
  showInspectionStatuses = true,
}: Props) {
  if (!diff || !diff.diffRegions?.length) {
    return null;
  }

  const prepared: Array<{
    resolved: ResolvedOverlayRegion;
    inspectionTone: OverlayInspectionTone;
  }> = [];

  for (const region of diff.diffRegions) {
    if (!includeRegionWhenChangesOnly(region, diff, showChangesOnly)) {
      continue;
    }
    const resolved = resolveOverlayRegion(region);
    if (!resolved) continue;
    prepared.push({
      resolved,
      inspectionTone: regionOverlayTone(region, diff, showInspectionStatuses),
    });
  }

  if (!prepared.length) {
    return null;
  }

  return (
    <svg
      className="pointer-events-none absolute left-0 top-0 z-[15]"
      width={viewerSize.width}
      height={viewerSize.height}
      viewBox={`0 0 ${viewerSize.width} ${viewerSize.height}`}
      data-testid="drawing-overlay-layer"
    >
      {prepared.map((item, index) => (
        <DiffOverlayShape
          key={`${diff.id}-${index}`}
          region={item.resolved}
          viewerSize={viewerSize}
          selected
          index={index}
          inspectionTone={item.inspectionTone}
        />
      ))}
    </svg>
  );
}
