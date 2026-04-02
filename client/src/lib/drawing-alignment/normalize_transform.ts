import { invert3, multiply3 } from "@/lib/drawing-alignment/matrix3";

/** Build 3×3 row-major H (sub natural → master natural) from API transform. */
export function alignmentToNaturalHomography3x3(transform: {
  type: "identity" | "affine" | "homography";
  matrix: number[];
}): number[] | null {
  const { type, matrix: m } = transform;
  if (type === "identity") {
    if (m.length === 0) {
      return [1, 0, 0, 0, 1, 0, 0, 0, 1];
    }
    if (m.length >= 9) {
      return m.slice(0, 9);
    }
    if (m.length >= 6) {
      const [a, b, tx, c, d, ty] = m;
      return [a, b, tx, c, d, ty, 0, 0, 1];
    }
    return null;
  }
  if (type === "affine") {
    if (m.length < 6) return null;
    const [a, b, tx, c, d, ty] = m;
    return [a, b, tx, c, d, ty, 0, 0, 1];
  }
  if (type === "homography") {
    if (m.length < 9) return null;
    return m.slice(0, 9);
  }
  return null;
}

/**
 * Affine map from natural image coords (origin top-left) to the same render box used for
 * object-fit: contain (scale + centered letterbox).
 */
export function objectContainAffine(
  naturalW: number,
  naturalH: number,
  renderW: number,
  renderH: number
): number[] {
  if (naturalW <= 0 || naturalH <= 0 || renderW <= 0 || renderH <= 0) {
    return [1, 0, 0, 0, 1, 0, 0, 0, 1];
  }
  const s = Math.min(renderW / naturalW, renderH / naturalH);
  const dw = s * naturalW;
  const dh = s * naturalH;
  const ox = (renderW - dw) / 2;
  const oy = (renderH - dh) / 2;
  return [s, 0, ox, 0, s, oy, 0, 0, 1];
}

/**
 * Backend homography H maps homogeneous sub **natural pixel** coords → master **natural pixel** coords
 * (OpenCV findHomography on rendered page rasters). Re-express in **CSS render box** pixels
 * where both images use the same container with object-contain.
 *
 * H_disp = T_m · H · T_s⁻¹
 */
export function homographyNaturalToRender(
  H: number[],
  masterNatural: { w: number; h: number },
  subNatural: { w: number; h: number },
  renderBox: { w: number; h: number }
): number[] | null {
  if (H.length < 9) return null;

  const Tm = objectContainAffine(masterNatural.w, masterNatural.h, renderBox.w, renderBox.h);
  const Ts = objectContainAffine(subNatural.w, subNatural.h, renderBox.w, renderBox.h);
  const TsInv = invert3(Ts);
  if (!TsInv) return null;

  return multiply3(multiply3(Tm, H), TsInv);
}

/**
 * Affine 6-tuple [a,b,tx,c,d,ty] as 3×3 bottom row [0,0,1], then same composition as homography.
 */
export function affineNaturalToRender(
  affine6: number[],
  masterNatural: { w: number; h: number },
  subNatural: { w: number; h: number },
  renderBox: { w: number; h: number }
): number[] | null {
  if (affine6.length < 6) return null;
  const [a, b, tx, c, d, ty] = affine6;
  const H = [a, b, tx, c, d, ty, 0, 0, 1];
  return homographyNaturalToRender(H, masterNatural, subNatural, renderBox);
}
