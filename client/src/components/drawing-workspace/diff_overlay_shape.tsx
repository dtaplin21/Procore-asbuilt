import type { ResolvedOverlayRegion, ViewerSize } from "@/lib/drawing-overlays/overlay-types";
import {
  normalizedPointsToPixels,
  normalizedRectToPixels,
  polygonPointsToSvgString,
} from "@/lib/drawing-overlays/geometry";

type Props = {
  region: ResolvedOverlayRegion;
  viewerSize: ViewerSize;
  selected?: boolean;
  index: number;
};

export default function DiffOverlayShape({
  region,
  viewerSize,
  selected = false,
  index,
}: Props) {
  const strokeWidth = selected ? 3 : 2;
  const stroke = selected ? "#dc2626" : "#f97316";
  const fill = selected ? "rgba(220, 38, 38, 0.16)" : "rgba(249, 115, 22, 0.14)";

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
