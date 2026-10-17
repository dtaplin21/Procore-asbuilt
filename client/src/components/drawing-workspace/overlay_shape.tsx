import type { ResolvedOverlayRegion, ViewerSize } from "@/lib/drawing-overlays/overlay-types";
import {
  normalizedPointsToPixels,
  normalizedRectToPixels,
  polygonPointsToSvgString,
} from "@/lib/drawing-overlays/geometry";
import {
  isUtilityLineScope,
  overlayColorsForTone,
  utilityPolylineHighlightStyle,
  utilityPolylineStrokeWidth,
  type OverlayInspectionTone,
} from "@/lib/drawing-overlays/inspection_overlay";

type Props = {
  region: ResolvedOverlayRegion;
  viewerSize: ViewerSize;
  selected?: boolean;
  index: number;
  regionId?: number | string;
  /** Pass/fail/changed tone, or `neutral` when status coloring is hidden. */
  inspectionTone: OverlayInspectionTone;
  label?: string | null;
};

/** SVG rect, polygon, or polyline for one normalized overlay region (master drawing space). */
export default function OverlayShape({
  region,
  viewerSize,
  selected = false,
  index,
  regionId,
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
      <g
        data-testid={`overlay-group-${index}`}
        data-overlay-id={regionId != null ? String(regionId) : undefined}
        data-focused={selected ? "true" : "false"}
      >
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

  if (region.kind === "line_segments") {
    const utilityHighlight = isUtilityLineScope(region.source.scopeKind)
      ? utilityPolylineHighlightStyle(selected)
      : null;
    const segmentStroke = utilityPolylineStrokeWidth(selected);
    const pixelSegments = region.segments.map(([start, end]) => ({
      start: normalizedPointsToPixels([start], viewerSize)[0],
      end: normalizedPointsToPixels([end], viewerSize)[0],
    }));
    const labelAnchor = pixelSegments[0]?.start;

    return (
      <g
        data-testid={`overlay-group-${index}`}
        data-overlay-id={regionId != null ? String(regionId) : undefined}
        data-focused={selected ? "true" : "false"}
        data-overlay-highlight={utilityHighlight ? "utility-marker" : undefined}
      >
        {pixelSegments.map((segment, segmentIndex) => (
          <line
            key={`segment-${segmentIndex}`}
            x1={segment.start.x}
            y1={segment.start.y}
            x2={segment.end.x}
            y2={segment.end.y}
            stroke={utilityHighlight?.stroke ?? stroke}
            strokeWidth={utilityHighlight?.strokeWidth ?? segmentStroke}
            strokeLinecap="round"
            style={
              utilityHighlight
                ? { mixBlendMode: utilityHighlight.mixBlendMode }
                : undefined
            }
            data-testid={`overlay-line-segment-${index}-${segmentIndex}`}
          />
        ))}
        {caption && labelAnchor ? (
          <text
            x={labelAnchor.x + 4}
            y={Math.max(12, labelAnchor.y - 6)}
            fill={utilityHighlight?.labelFill ?? stroke}
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

  if (region.kind === "polyline") {
    const points = normalizedPointsToPixels(region.points, viewerSize);
    const pointsString = polygonPointsToSvgString(points);
    const utilityHighlight = isUtilityLineScope(region.source.scopeKind)
      ? utilityPolylineHighlightStyle(selected)
      : null;
    const polylineStroke = utilityPolylineStrokeWidth(selected);

    return (
      <g
        data-testid={`overlay-group-${index}`}
        data-overlay-id={regionId != null ? String(regionId) : undefined}
        data-focused={selected ? "true" : "false"}
        data-overlay-highlight={utilityHighlight ? "utility-marker" : undefined}
      >
        <polyline
          points={pointsString}
          fill="none"
          stroke={utilityHighlight?.stroke ?? stroke}
          strokeWidth={utilityHighlight?.strokeWidth ?? polylineStroke}
          strokeLinecap="round"
          strokeLinejoin="round"
          style={
            utilityHighlight
              ? { mixBlendMode: utilityHighlight.mixBlendMode }
              : undefined
          }
          data-testid={`overlay-polyline-${index}`}
        />
        {caption && points[0] ? (
          <text
            x={points[0].x + 4}
            y={Math.max(12, points[0].y - 6)}
            fill={utilityHighlight?.labelFill ?? stroke}
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
