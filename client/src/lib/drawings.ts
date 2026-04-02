import type { DrawingTransform } from "@shared/schema";

export function validateTransform(transform: unknown): {
  valid: boolean;
  reason?: string;
} {
  if (transform === null || transform === undefined) {
    return { valid: false, reason: "Transform is null or undefined" };
  }

  if (typeof transform === "string") {
    return {
      valid: false,
      reason:
        "Transform is a JSON string (backend should return a parsed object, not json.dumps)",
    };
  }

  if (typeof transform !== "object") {
    return { valid: false, reason: "Transform is not an object" };
  }

  const t = transform as Partial<DrawingTransform>;

  if (
    t.type !== "identity" &&
    t.type !== "affine" &&
    t.type !== "homography"
  ) {
    return { valid: false, reason: "Invalid transform.type" };
  }

  if (!Array.isArray(t.matrix)) {
    return { valid: false, reason: "Transform matrix is not an array" };
  }

  const len = t.matrix.length;

  if (t.type === "identity") {
    if (len !== 0 && len !== 6 && len !== 9) {
      return {
        valid: false,
        reason: "Identity transform matrix must be empty, 6, or 9 numbers",
      };
    }
  } else if (t.type === "affine") {
    if (len !== 6) {
      return { valid: false, reason: "Affine transform must have 6 numbers" };
    }
  } else if (t.type === "homography") {
    if (len !== 9) {
      return {
        valid: false,
        reason: "Homography transform must have 9 numbers",
      };
    }
  }

  if (!t.matrix.every((n) => typeof n === "number" && Number.isFinite(n))) {
    return {
      valid: false,
      reason: "Transform matrix contains non-numbers or non-finite values",
    };
  }

  return { valid: true };
}
