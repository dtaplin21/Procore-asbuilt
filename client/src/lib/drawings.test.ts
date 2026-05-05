import { describe, expect, it } from "vitest";

import { validateTransform } from "@/lib/drawings";

describe("validateTransform", () => {
  it("accepts affine 3×3 identity from API (9 numbers)", () => {
    const r = validateTransform({
      type: "affine",
      matrix: [1, 0, 0, 0, 1, 0, 0, 0, 1],
      confidence: 1,
      meta: { note: "Identity transform for MVP overlay behavior" },
    });
    expect(r).toEqual({ valid: true });
  });

  it("accepts affine 2×3 (6 numbers)", () => {
    expect(
      validateTransform({ type: "affine", matrix: [1, 0, 0, 0, 1, 0] })
    ).toEqual({ valid: true });
  });

  it("coerces numeric strings in matrix", () => {
    expect(
      validateTransform({
        type: "affine",
        matrix: ["1", "0", "0", "0", "1", "0", "0", "0", "1"],
      })
    ).toEqual({ valid: true });
  });

  it("rejects affine with wrong length", () => {
    const r = validateTransform({ type: "affine", matrix: [1, 0, 0, 0, 1] });
    expect(r.valid).toBe(false);
    expect(r.reason).toContain("6 or 9");
  });
});
