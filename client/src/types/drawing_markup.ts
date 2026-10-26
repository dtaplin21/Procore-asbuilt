export type MarkupKind = "polyline" | "cloud" | "arrow" | "rect" | "text";
export type MarkupTool = MarkupKind | "select";

/** A point in display-frame fractions: x and y in [0, 1], y = 0 at the top of the rendered page. */
export type Pt = [number, number];

export interface DrawingMarkup {
  id: number;
  drawingId: number;
  page: number;
  kind: MarkupKind;
  points: Pt[];
  label: string | null;
  inspectionType: string | null;
  status: string | null;
  color: string | null;
  createdBy: string;
  createdAt: string;
  updatedAt: string;
}

export interface NewMarkup {
  page: number;
  kind: MarkupKind;
  points: Pt[];
  label?: string | null;
  inspectionType?: string | null;
  status?: string | null;
  color?: string | null;
}

export interface MarkupSummaryRow {
  inspection_type: string | null;
  status: string | null;
  count: number;
}
