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
  /** When set, only the matching overlay is drawn with emphasis; others are muted. */
  focusedOverlayId?: string | null;
  /** When true, only regions that are still "changed" (or not yet reviewed) are drawn. */
  showChangesOnly?: boolean;
  /** When false, all regions use the same highlight (amber); no passed/failed coloring. */
  showInspectionStatuses?: boolean;
};

function overlayMatchesFocus(regionId: number | string, focusedOverlayId: string | null | undefined): boolean {
  if (focusedOverlayId == null || focusedOverlayId === "") return true;
  return String(regionId) === String(focusedOverlayId);
}

export default function DrawingOverlayLayer({
  regions,
  viewerSize,
  focusedOverlayId = null,
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
    label: string | null;
    regionId: number | string;
    emphasized: boolean;
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
      label: region.label,
      regionId: region.id,
      emphasized: overlayMatchesFocus(region.id, focusedOverlayId),
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
          selected={item.emphasized}
          index={index}
          regionId={item.regionId}
          inspectionTone={item.inspectionTone}
          label={item.label}
        />
      ))}
    </svg>
  );
}
