export type PerceptionPoint = { x: number; y: number };

export type PerceptionBox = {
  x: number;
  y: number;
  width: number;
  height: number;
};

export type PerceptionOcr = {
  id: string;
  text: string;
  bbox: PerceptionBox;
  confidence: number;
  category?: string;
  isStationLabel: boolean;
  stationLabel?: string;
  parsedStation?: number;
  source?: string;
};

export type PerceptionSsmh = {
  id: string;
  label?: string;
  point: PerceptionPoint;
  surveyNE?: { n: number; e: number };
  confidence: number;
  source: string;
};

export type PerceptionPipe = {
  id: string;
  polyline: PerceptionPoint[];
  source: string;
  confidence?: number | null;
};

export type PerceptionContour = {
  id: string;
  points: PerceptionPoint[];
  huMoments: number[];
  role?: string;
  contourStored?: boolean;
};

export type PerceptionControl = {
  id: string;
  masterPt: PerceptionPoint;
  origin: "auto" | "manual";
  surveyNE?: { n: number; e: number };
  label?: string;
};

export type PerceptionRegion = {
  id: string;
  name: string;
  polygon: PerceptionPoint[];
  status: string;
};

export type PerceptionOverlay = {
  id: string;
  regionId?: string | null;
  polyline: PerceptionPoint[];
  evidenceRunId: string;
  source?: string;
};

export type MasterPerception = {
  master: {
    id: string;
    drawingNumber: string;
    page: number;
    imageUrl: string;
    widthPx: number;
    heightPx: number;
    projectId: number | null;
  };
  ocr: PerceptionOcr[];
  ssmh: PerceptionSsmh[];
  pipes: PerceptionPipe[];
  edges: null;
  contours: PerceptionContour[];
  controlPoints: PerceptionControl[];
  registration: {
    evidenceRunId: string;
    transform: { scale: number; rotationDeg: number; tx: number; ty: number } | null;
    rmsResidualPx: number | null;
    pointCount: number;
    collinearityScore: number;
    quality: "ok" | "warn" | "fail";
  };
  regions: PerceptionRegion[];
  overlays: PerceptionOverlay[];
  warnings: string[];
};

export type PerceptionLayers = {
  ocr: boolean;
  stations: boolean;
  vocabulary: boolean;
  ssmh: boolean;
  pipes: boolean;
  contours: boolean;
  controls: boolean;
  overlays: boolean;
  regions: boolean;
};

export const DEFAULT_LAYERS: PerceptionLayers = {
  ocr: true,
  stations: true,
  vocabulary: true,
  ssmh: true,
  pipes: true,
  contours: false,
  controls: true,
  overlays: true,
  regions: true,
};

export const VOCAB_COLORS: Record<string, string> = {
  project_identifier: "#0f766e",
  inspection_type: "#1d4ed8",
  inspection_status: "#7c3aed",
  location_term: "#b45309",
  trade_term: "#be123c",
  drawing_term: "#0369a1",
  sheet_identifier: "#0e7490",
  document_reference: "#4338ca",
  markup_term: "#a16207",
  field_condition_term: "#9f1239",
  inspection_action_term: "#166534",
  confidence_label: "#52525b",
};

export function confidenceColor(confidence: number): string {
  if (confidence < 0.5) return "#dc2626";
  if (confidence < 0.8) return "#d97706";
  return "#15803d";
}

export function pointsAttr(points: PerceptionPoint[]): string {
  return points.map((point) => `${point.x},${point.y}`).join(" ");
}

export function pipePath(pipes: PerceptionPipe[]): string {
  return pipes
    .map((pipe) => {
      if (pipe.polyline.length < 2) return "";
      const [first, ...rest] = pipe.polyline;
      return `M ${first.x} ${first.y} ${rest.map((point) => `L ${point.x} ${point.y}`).join(" ")}`;
    })
    .filter(Boolean)
    .join(" ");
}
