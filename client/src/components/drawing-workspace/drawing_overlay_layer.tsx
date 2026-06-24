import type { OverlayRegion, ResolvedOverlayRegion, ViewerSize } from "@/lib/drawing-overlays/overlay-types";
import { resolveOverlayRegion } from "@/lib/drawing-overlays/geometry";
import {
  includeOverlayWhenChangesOnly,
  overlayRegionTone,
  type OverlayInspectionTone,
} from "@/lib/drawing-overlays/inspection_overlay";
import OverlayShape from "@/components/drawing-workspace/overlay_shape";

type Props = {
  /** Normalized regions in master drawing space (no alignment warp). */
  regions: OverlayRegion[];
  viewerSize: ViewerSize;
  /** When true, only regions that are still "changed" (or not yet reviewed) are drawn. */
  showChangesOnly?: boolean;
  /** When false, all regions use the same highlight (amber); no passed/failed coloring. */
  showInspectionStatuses?: boolean;
};

export default function DrawingOverlayLayer({
  regions,
  viewerSize,
  showChangesOnly = false,
  showInspectionStatuses = true,
}: Props) {
  if (!regions.length) {
    return null;
  }

  const prepared: Array<{
    key: string;
    resolved: ResolvedOverlayRegion;
    inspectionTone: OverlayInspectionTone;
  }> = [];

  for (const region of regions) {
    if (!includeOverlayWhenChangesOnly(region, showChangesOnly)) {
      continue;
    }
    const resolved = resolveOverlayRegion(region.shape);
    if (!resolved) continue;
    prepared.push({
      key: `${region.kind}-${region.id}`,
      resolved,
      inspectionTone: overlayRegionTone(region, showInspectionStatuses),
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
        <OverlayShape
          key={item.key}
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
