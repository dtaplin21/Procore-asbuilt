import type { DrawingDiff } from "@/types/drawing_workspace";
import type { ViewerSize } from "@/lib/drawing-overlays/overlay-types";
import { resolveOverlayRegion } from "@/lib/drawing-overlays/geometry";
import DiffOverlayShape from "@/components/drawing-workspace/diff_overlay_shape";

type Props = {
  diff: DrawingDiff | null;
  viewerSize: ViewerSize;
};

export default function DrawingOverlayLayer({ diff, viewerSize }: Props) {
  if (!diff || !diff.diffRegions?.length) {
    return null;
  }

  const resolvedRegions = diff.diffRegions
    .map((region) => resolveOverlayRegion(region))
    .filter(Boolean);

  if (!resolvedRegions.length) {
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
      {resolvedRegions.map((region, index) => (
        <DiffOverlayShape
          key={`${diff.id}-${index}`}
          region={region!}
          viewerSize={viewerSize}
          selected
          index={index}
        />
      ))}
    </svg>
  );
}
