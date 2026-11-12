import type { PerceptionLayers, PerceptionPipe, MasterPerception } from "@/lib/testing/perception_model";
import { confidenceColor, pipePath, pointsAttr, VOCAB_COLORS } from "@/lib/testing/perception_model";

type Props = {
  perception: MasterPerception;
  layers: PerceptionLayers;
  minConfidence: number;
  showImage: boolean;
  imageUrl: string;
  diff: boolean;
  crosshair: { x: number; y: number } | null;
  onHover: (point: { x: number; y: number } | null) => void;
  onSelect: (feature: unknown) => void;
};

const HAIRLINE = { strokeWidth: 1.25, vectorEffect: "non-scaling-stroke" as const };
const PIPE_STROKE = { strokeWidth: 0.7, vectorEffect: "non-scaling-stroke" as const };

function visibleOcr(perception: MasterPerception, layers: PerceptionLayers, minConfidence: number) {
  return perception.ocr.filter((item) => {
    if (item.confidence < minConfidence) return false;
    if (item.isStationLabel && layers.stations) return true;
    if (item.category && layers.vocabulary) return true;
    return layers.ocr;
  });
}

export function PerceptionSheet({
  perception,
  layers,
  minConfidence,
  showImage,
  imageUrl,
  diff,
  crosshair,
  onHover,
  onSelect,
}: Props) {
  const { widthPx, heightPx } = perception.master;
  const digitized = perception.pipes.filter((pipe) => pipe.source === "sheet_digitization");
  const approximate = perception.pipes.filter((pipe) => pipe.source !== "sheet_digitization");
  const ocr = visibleOcr(perception, layers, minConfidence);
  const mark = Math.max(widthPx, heightPx) * 0.012;

  return (
    <svg
      className="h-full w-full"
      viewBox={`0 0 ${widthPx} ${heightPx}`}
      preserveAspectRatio="xMidYMid meet"
      data-testid={showImage ? "perception-original" : "perception-redraw"}
      onMouseMove={(event) => {
        const svg = event.currentTarget;
        const matrix = svg.getScreenCTM();
        if (!matrix) return;
        const point = svg.createSVGPoint();
        point.x = event.clientX;
        point.y = event.clientY;
        const local = point.matrixTransform(matrix.inverse());
        onHover({ x: local.x, y: local.y });
      }}
      onMouseLeave={() => onHover(null)}
      style={{ background: showImage ? "transparent" : "#fff", display: "block" }}
    >
      <rect
        x={0}
        y={0}
        width={widthPx}
        height={heightPx}
        fill={showImage ? "#f8fafc" : "#fff"}
        stroke="#cbd5e1"
        {...HAIRLINE}
      />
      {showImage && imageUrl ? (
        <image href={imageUrl} width={widthPx} height={heightPx} />
      ) : null}
      {layers.regions
        ? perception.regions.map((region) => (
            <polygon
              key={region.id}
              data-testid={`region-${region.id}`}
              points={pointsAttr(region.polygon)}
              fill={diff ? "transparent" : "rgba(37,99,235,0.12)"}
              stroke="#2563eb"
              {...HAIRLINE}
              onClick={() => onSelect(region)}
            />
          ))
        : null}
      {layers.contours
        ? perception.contours.map((contour) => (
            <polygon
              key={contour.id}
              data-testid={`contour-${contour.id}`}
              points={pointsAttr(contour.points)}
              fill="none"
              stroke="#64748b"
              {...HAIRLINE}
              onClick={() => onSelect(contour)}
            />
          ))
        : null}
      {layers.pipes && (!showImage || diff) ? (
        <>
          <path
            data-testid="pipes-digitized"
            d={pipePath(digitized)}
            fill="none"
            stroke={diff ? "#dc2626" : "#111827"}
            {...PIPE_STROKE}
            opacity={diff ? 0.45 : 0.22}
          />
          <PipeSet pipes={approximate} diff={diff} onSelect={onSelect} />
        </>
      ) : null}
      {layers.overlays
        ? perception.overlays.map((overlay) => (
            <polyline
              key={overlay.id}
              data-testid={`overlay-${overlay.id}`}
              points={pointsAttr(overlay.polyline)}
              fill="none"
              stroke="#ca8a04"
              {...HAIRLINE}
              onClick={() => onSelect(overlay)}
            />
          ))
        : null}
      {layers.ssmh
        ? perception.ssmh.map((item) => (
            <g key={item.id} data-testid={`ssmh-${item.id}`} onClick={() => onSelect(item)}>
              <circle cx={item.point.x} cy={item.point.y} r={mark} fill="none" stroke="#b91c1c" {...HAIRLINE} />
              {item.label ? (
                <text x={item.point.x + mark} y={item.point.y} fontSize={mark * 1.4} fill="#b91c1c">
                  {item.label}
                </text>
              ) : null}
            </g>
          ))
        : null}
      {ocr.map((item) => {
        const color = item.category
          ? VOCAB_COLORS[item.category] ?? confidenceColor(item.confidence)
          : confidenceColor(item.confidence);
        return (
          <g key={item.id} data-testid={`ocr-${item.id}`} onClick={() => onSelect(item)}>
            <rect
              x={item.bbox.x}
              y={item.bbox.y}
              width={Math.max(item.bbox.width, 1)}
              height={Math.max(item.bbox.height, 1)}
              fill={item.isStationLabel ? "rgba(250,204,21,0.35)" : "none"}
              stroke={color}
              {...HAIRLINE}
            />
            <text
              x={item.bbox.x}
              y={item.bbox.y + item.bbox.height}
              fontSize={Math.max(item.bbox.height * 0.85, 1)}
              fill={color}
            >
              {item.isStationLabel && item.parsedStation != null
                ? `${item.text} (${item.parsedStation})`
                : item.text}
            </text>
          </g>
        );
      })}
      {layers.controls
        ? perception.controlPoints.map((point, index) => (
            <g key={point.id} data-testid={`control-${point.id}`} onClick={() => onSelect(point)}>
              <circle
                cx={point.masterPt.x}
                cy={point.masterPt.y}
                r={mark * 0.7}
                fill={point.origin === "manual" ? "#7c3aed" : "#0891b2"}
              />
              <text x={point.masterPt.x + mark} y={point.masterPt.y - mark * 0.4} fontSize={mark} fill="#0f172a">
                {index + 1}
              </text>
            </g>
          ))
        : null}
      {crosshair ? (
        <g data-testid={showImage ? "crosshair-original" : "crosshair-redraw"} pointerEvents="none">
          <line x1={crosshair.x} y1={0} x2={crosshair.x} y2={heightPx} stroke="#f97316" {...HAIRLINE} />
          <line x1={0} y1={crosshair.y} x2={widthPx} y2={crosshair.y} stroke="#f97316" {...HAIRLINE} />
        </g>
      ) : null}
    </svg>
  );
}

function PipeSet({
  pipes,
  diff,
  onSelect,
}: {
  pipes: PerceptionPipe[];
  diff: boolean;
  onSelect: (feature: unknown) => void;
}) {
  return (
    <g data-testid="pipes-approx">
      {pipes.map((pipe) => (
        <polyline
          key={pipe.id}
          points={pointsAttr(pipe.polyline)}
          fill="none"
          stroke={diff ? "#dc2626" : "#b45309"}
          {...HAIRLINE}
          strokeDasharray="6 4"
          opacity={diff ? 0.5 : 1}
          onClick={() => onSelect(pipe)}
        />
      ))}
    </g>
  );
}
