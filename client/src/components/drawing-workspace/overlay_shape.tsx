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
  /** Pass/fail/changed tone, or `neutral` when status coloring is hidden. */
  inspectionTone: OverlayInspectionTone;
  label?: string | null;
};

/** SVG rect/polygon for one normalized overlay region (master drawing space). */
export default function OverlayShape({
  region,
  viewerSize,
  selected = false,
  index,
  inspectionTone,
  label = null,
}: Props) {
  const { stroke, fill, strokeWidth } = overlayColorsForTone(inspectionTone, selected);
  const caption =
    label && label.trim().length > 0
      ? label.trim().length > 48
        ? `${label.trim().slice(0, 45)}…`
        : label.trim()
      : null;

  if (region.kind === "rect") {
    const rect = normalizedRectToPixels(region.rect, viewerSize);

    return (
      <g data-testid={`overlay-group-${index}`}>
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
          data-testid={`overlay-rect-${index}`}
        />
        {caption ? (
          <text
            x={rect.x + 4}
            y={Math.max(12, rect.y - 6)}
            fill={stroke}
            fontSize={11}
            fontWeight={600}
            data-testid={`overlay-label-${index}`}
          >
            {caption}
          </text>
        ) : null}
      </g>
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
      data-testid={`overlay-polygon-${index}`}
    />
  );
}
