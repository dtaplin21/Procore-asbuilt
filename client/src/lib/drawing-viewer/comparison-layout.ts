/**
 * Compute a single pixel render box for master + sub overlay so both layers share
 * the same coordinate system. Uses master natural aspect ratio and caps by max width / viewport height.
 *
 * If master and sub have different intrinsic aspect ratios, the backend transform must already
 * map between those spaces; visually aligning also requires matching render boxes (object-contain in the same box).
 */
export function computeComparisonRenderBox(
  naturalWidth: number,
  naturalHeight: number,
  availableWidth: number,
  options?: { maxCssWidth?: number; maxViewportHeightFraction?: number }
): { width: number; height: number } {
  const maxCssWidth = options?.maxCssWidth ?? 1200;
  const vhFrac = options?.maxViewportHeightFraction ?? 0.8;

  if (naturalWidth <= 0 || naturalHeight <= 0 || availableWidth <= 0) {
    return { width: 0, height: 0 };
  }

  const maxW = Math.min(maxCssWidth, availableWidth);
  const maxH =
    typeof window !== "undefined" ? window.innerHeight * vhFrac : (naturalHeight / naturalWidth) * maxW;

  let width = maxW;
  let height = (width * naturalHeight) / naturalWidth;

  if (height > maxH) {
    height = maxH;
    width = (height * naturalWidth) / naturalHeight;
  }

  return { width, height };
}
