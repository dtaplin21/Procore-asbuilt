import type { DrawingTransform } from "@shared/schema";

import { affineMatrixToCssMatrix2d } from "@/lib/drawing-alignment/css_transform";

type Props = {
  src: string;
  alt: string;
  transform: DrawingTransform;
  opacity: number;
};

/**
 * Maps `DrawingTransform` to CSS `matrix()` using one convention (see shared/schema + css_transform).
 * MVP: affine (6) first; homography (9) uses the 2×3 affine block of H; identity falls back to I₂.
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
 * Sub drawing composited above the master in the same `relative` container (`absolute inset-0`).
 */
export default function AlignedSubOverlay({ src, alt, transform, opacity }: Props) {
  const cssTransform = toCssMatrix(transform);

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
      data-testid="aligned-sub-overlay"
      draggable={false}
    />
  );
}
