/**
 * Thin re-export — per the file map, this may be merged into
 * use-drawing-regions.ts; kept as a separate named import path here so
 * Objects' region layer (PR4) can import just the summary hook without
 * pulling in the CRUD mutations it doesn't need.
 */

export { useRegionInspectionSummary, regionInspectionSummaryQueryKey } from "@/hooks/use-drawing-regions";
