import { useMemo, type SyntheticEvent } from "react";

import type { DrawingTransform } from "@shared/schema";

import {
  affineMatrixToCssMatrix2d,
  homographyRowMajorToMatrix3dCss,
} from "@/lib/drawing-alignment/css_transform";
import {
  alignmentToNaturalHomography3x3,
  homographyNaturalToRender,
} from "@/lib/drawing-alignment/normalize_transform";

type Size2 = { w: number; h: number };

type Props = {
  src: string;
  alt: string;
  transform: DrawingTransform;
  opacity: number;
  /** When set with sub natural + render box, alignment is composed into CSS render pixels (object-contain). */
  masterNatural?: Size2 | null;
  subNatural?: Size2 | null;
  renderBox?: Size2 | null;
  /** Fires when the sub image loads (use to read naturalWidth / naturalHeight). */
  onLoad?: (e: SyntheticEvent<HTMLImageElement>) => void;
};

/**
 * Maps `DrawingTransform` to CSS `matrix()` / `matrix3d()` using one convention (see shared/schema + css_transform).
 * When master/sub natural sizes and the shared render box are known, applies H_disp = T_m · H · T_s⁻¹ so the
 * transform matches the same object-contain layout as the master (avoids drift vs raw pixel alignment).
 */
export function toCssMatrix(transform: DrawingTransform): string {
  const m = transform.matrix;

  if (transform.type === "affine" && m.length === 6) {
    return affineMatrixToCssMatrix2d(m);
  }

  if (transform.type === "identity") {
    if (m.length === 0) {
      return "matrix(1, 0, 0, 1, 0, 0)";
    }
    return affineMatrixToCssMatrix2d(m);
  }

  if (transform.type === "homography" && m.length >= 9) {
    return affineMatrixToCssMatrix2d(m);
  }

  if (m.length >= 6) {
    return affineMatrixToCssMatrix2d(m);
  }

  return "matrix(1, 0, 0, 1, 0, 0)";
}

/**
 * Sub drawing composited above the master. The parent must be `position: relative` with an
 * explicit width and height (same render box as the master) so `absolute inset-0` + `object-contain`
 * matches the master layer.
 */
export default function AlignedSubOverlay({
  src,
  alt,
  transform,
  opacity,
  masterNatural,
  subNatural,
  renderBox,
  onLoad,
}: Props) {
  const matrixKey = transform.matrix.join(",");

  const cssTransform = useMemo(() => {
    const rb = renderBox;
    const mn = masterNatural;
    const sn = subNatural;
    if (
      rb &&
      mn &&
      sn &&
      mn.w > 0 &&
      mn.h > 0 &&
      sn.w > 0 &&
      sn.h > 0 &&
      rb.w > 0 &&
      rb.h > 0
    ) {
      const Hn = alignmentToNaturalHomography3x3(transform);
      if (Hn) {
        const Hdisp = homographyNaturalToRender(Hn, mn, sn, rb);
        if (Hdisp) {
          return homographyRowMajorToMatrix3dCss(Hdisp);
        }
      }
    }
    return toCssMatrix(transform);
  }, [
    transform.type,
    matrixKey,
    masterNatural?.w,
    masterNatural?.h,
    subNatural?.w,
    subNatural?.h,
    renderBox?.w,
    renderBox?.h,
  ]);

  return (
    <img
      src={src}
      alt={alt}
      className="pointer-events-none absolute inset-0 z-[5] h-full w-full select-none object-contain"
      style={{
        opacity,
        transform: cssTransform,
        transformOrigin: "top left",
      }}
      onLoad={onLoad}
      data-testid="aligned-sub-overlay"
      draggable={false}
    />
  );
}
