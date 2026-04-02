/**
 * Affine / homography flat matrix → CSS `matrix(a, b, c, d, e, f)`.
 *
 * **Convention (matches backend overlay transform):** affine 6-tuple is
 *   `[a, b, tx, c, d, ty]`  =  first row (a, b, tx), second row (c, d, ty) of the 2×3.
 * CSS 2D `matrix(a, b, c, d, e, f)` is `[[a, c, e], [b, d, f]]`, so:
 *   `matrix(a, c, b, d, tx, ty)`.
 *
 * For 9 numbers (row-major 3×3 homography), the first six entries are the same 2×3 affine block.
 */
export function affineMatrixToCssMatrix2d(matrix: number[]): string {
  if (matrix.length >= 9) {
    const a = matrix[0];
    const b = matrix[1];
    const tx = matrix[2];
    const c = matrix[3];
    const d = matrix[4];
    const ty = matrix[5];
    return `matrix(${a}, ${c}, ${b}, ${d}, ${tx}, ${ty})`;
  }
  if (matrix.length >= 6) {
    const [a, b, tx, c, d, ty] = matrix;
    return `matrix(${a}, ${c}, ${b}, ${d}, ${tx}, ${ty})`;
  }
  return "matrix(1, 0, 0, 1, 0, 0)";
}
