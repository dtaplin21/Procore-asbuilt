/**
 * Shared types for the region-visibility spec (PR1–5). Wire shapes mirror
 * backend/models/schemas.py (DrawingRegion*, RegionInspectionSummary*) and
 * shared/schema.ts — reconciled with this codebase:
 *
 *   - Integer IDs (`regionId`, `masterDrawingId`), not string UUIDs
 *   - Normalized 0–1 geometry (`{ type: "rect" | "polygon", … }`), not pixel
 *     x/y/width/height/pageWidth/pageHeight columns
 *   - Flat snake_case API fields on CRUD responses (`inspection_type_tags`, …)
 *   - Routes scoped under `/api/projects/{projectId}/drawings/{masterDrawingId}/…`
 */

export type {
  DrawingRegionCreate,
  DrawingRegionGeometry,
  DrawingRegionPolygonGeometry,
  DrawingRegionRectGeometry,
  DrawingRegionResponse,
  DrawingRegionUpdate,
  RegionInspectionSummaryEntry,
  RegionInspectionSummaryResponse,
} from "@shared/schema";

/** States returned by GET …/region-inspection-summary. */
export type RegionBackendState = "hidden" | "inspected";

/**
 * Full viewer display mode, including the admin "show inspectable areas" faint
 * outline (PR4). The backend never reports `setup_faint` — derive it locally
 * from the admin toggle (see region_display.ts when wired).
 */
export type RegionViewerState = RegionBackendState | "setup_faint";

/** POST /drawings/{masterDrawingId}/regions */
export type { DrawingRegionCreate as CreateDrawingRegionInput } from "@shared/schema";

/** PATCH /drawings/{masterDrawingId}/regions/{regionId} */
export type { DrawingRegionUpdate as UpdateDrawingRegionInput } from "@shared/schema";

/** GET /drawings/{masterDrawingId}/regions list item */
export type { DrawingRegionResponse as DrawingRegion } from "@shared/schema";

/** Tag fields edited in region_tag_form.tsx (maps to API snake_case on save). */
export interface DrawingRegionTags {
  inspectionTypeTags: string[];
  locationTags: string[];
}

/** Label + tags submitted from the region tag form. */
export interface RegionTagFormValues extends DrawingRegionTags {
  label: string;
}
