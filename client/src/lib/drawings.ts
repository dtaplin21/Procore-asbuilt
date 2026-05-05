import type { DrawingTransform } from "@shared/schema";

function matrixToFiniteNumbers(raw: unknown[]): number[] | null {
  const out: number[] = [];
  for (const n of raw) {
    if (typeof n === "number" && Number.isFinite(n)) {
      out.push(n);
      continue;
    }
    if (typeof n === "string" && n.trim() !== "") {
      const v = Number(n);
      if (Number.isFinite(v)) {
        out.push(v);
        continue;
      }
    }
    return null;
  }
  return out;
}

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

  const matrix = matrixToFiniteNumbers(t.matrix);
  if (matrix === null) {
    return {
      valid: false,
      reason: "Transform matrix contains non-numbers or non-finite values",
    };
  }

  const len = matrix.length;

  if (t.type === "identity") {
    if (len !== 0 && len !== 6 && len !== 9) {
      return {
        valid: false,
        reason: "Identity transform matrix must be empty, 6, or 9 numbers",
      };
    }
  } else if (t.type === "affine") {
    // Backend may send 2×3 affine (6) or full row-major 3×3 (9); normalize_transform uses the first 6.
    if (len !== 6 && len !== 9) {
      return {
        valid: false,
        reason: "Affine transform matrix must have 6 or 9 numbers",
      };
    }
  } else if (t.type === "homography") {
    if (len !== 9) {
      return {
        valid: false,
        reason: "Homography transform must have 9 numbers",
      };
    }
  }

  return { valid: true };
}
