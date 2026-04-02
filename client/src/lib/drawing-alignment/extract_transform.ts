import type {
  DrawingAlignmentListItem,
  DrawingAlignmentTransformResponse,
} from "@/types/drawing_workspace";

function isTransformType(
  v: unknown
): v is DrawingAlignmentTransformResponse["type"] {
  return v === "identity" || v === "affine" || v === "homography";
}

/** Normalize list/compare alignment payloads into a typed transform for the viewer. */
export function extractAlignmentTransform(
  item: DrawingAlignmentListItem | null
): DrawingAlignmentTransformResponse | null {
  if (!item) return null;

  if ("transform" in item && item.transform?.matrix?.length) {
    return item.transform;
  }

  const raw = "transformMatrix" in item ? item.transformMatrix : null;
  if (!raw || typeof raw !== "object") return null;

  const o = raw as Record<string, unknown>;
  const matrixRaw = o.matrix;
  if (!Array.isArray(matrixRaw) || matrixRaw.length < 6) return null;

  const matrix = matrixRaw.map((x) => Number(x));
  const type = o.type;
  return {
    type: isTransformType(type) ? type : "homography",
    matrix,
    confidence:
      o.confidence === null || o.confidence === undefined
        ? null
        : Number(o.confidence),
    meta:
      o.meta !== null && o.meta !== undefined && typeof o.meta === "object"
        ? (o.meta as Record<string, unknown>)
        : null,
  };
}
