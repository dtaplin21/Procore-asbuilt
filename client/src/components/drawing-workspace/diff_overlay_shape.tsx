import type { ResolvedOverlayRegion, ViewerSize } from "@/lib/drawing-overlays/overlay-types";
import {
  normalizedPointsToPixels,
  normalizedRectToPixels,
  polygonPointsToSvgString,
} from "@/lib/drawing-overlays/geometry";
import {
  overlayColorsForTone,
  type OverlayInspectionTone,
} from "@/lib/drawing-overlays/inspection_overlay";

type Props = {
  region: ResolvedOverlayRegion;
  viewerSize: ViewerSize;
  selected?: boolean;
  index: number;
  /** Inspection tone; `neutral` draws a single highlight when statuses are hidden. */
  inspectionTone: OverlayInspectionTone;
};

export default function DiffOverlayShape({
  region,
  viewerSize,
  selected = false,
  index,
  inspectionTone,
}: Props) {
  const { stroke, fill, strokeWidth } = overlayColorsForTone(inspectionTone, selected);

  if (region.kind === "rect") {
    const rect = normalizedRectToPixels(region.rect, viewerSize);

    return (
      <rect
        x={rect.x}
        y={rect.y}
        width={rect.width}
        height={rect.height}
        fill={fill}
        stroke={stroke}
        strokeWidth={strokeWidth}
        rx={4}
        ry={4}
        data-testid={`diff-overlay-rect-${index}`}
      />
    );
  }

  const points = normalizedPointsToPixels(region.points, viewerSize);
  const pointsString = polygonPointsToSvgString(points);

  return (
    <polygon
      points={pointsString}
      fill={fill}
      stroke={stroke}
      strokeWidth={strokeWidth}
      data-testid={`diff-overlay-polygon-${index}`}
    />
  );
}
