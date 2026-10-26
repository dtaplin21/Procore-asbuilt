import type { DrawingMarkup, Pt } from "../types/drawing_markup";

export const clamp01 = (v: number): number => (Number.isFinite(v) ? Math.min(1, Math.max(0, v)) : 0);

/** Pointer position to a display fraction of the element, clamped to the page. */
export function toFraction(rect: { left: number; top: number; width: number; height: number }, clientX: number, clientY: number): Pt {
  if (rect.width <= 0 || rect.height <= 0) return [0, 0];
  return [clamp01((clientX - rect.left) / rect.width), clamp01((clientY - rect.top) / rect.height)];
}

/** Distance from p to segment ab, in the same units as the inputs. */
export function distToSegment(p: Pt, a: Pt, b: Pt): number {
  const vx = b[0] - a[0];
  const vy = b[1] - a[1];
  const l2 = vx * vx + vy * vy;
  const t = l2 === 0 ? 0 : Math.max(0, Math.min(1, ((p[0] - a[0]) * vx + (p[1] - a[1]) * vy) / l2));
  return Math.hypot(p[0] - (a[0] + t * vx), p[1] - (a[1] + t * vy));
}

/** The outline of a markup as a list of vertices. Rectangles and clouds are closed. */
export function outline(m: Pick<DrawingMarkup, "kind" | "points">): Pt[] {
  const p = m.points;
  if (m.kind === "rect" && p.length === 2) {
    const [a, b] = p;
    return [[a[0], a[1]], [b[0], a[1]], [b[0], b[1]], [a[0], b[1]], [a[0], a[1]]];
  }
  if (m.kind === "cloud" && p.length >= 3) return [...p, p[0]];
  return p;
}

function inPolygon(pt: Pt, poly: Pt[]): boolean {
  let inside = false;
  for (let i = 0, j = poly.length - 1; i < poly.length; j = i++) {
    const [xi, yi] = poly[i];
    const [xj, yj] = poly[j];
    if (yi > pt[1] !== yj > pt[1] && pt[0] < ((xj - xi) * (pt[1] - yi)) / (yj - yi) + xi) inside = !inside;
  }
  return inside;
}

/** Distance from a point to a markup. Text is a point. Closed shapes count as 0 inside. */
export function distanceToMarkup(m: DrawingMarkup, pt: Pt): number {
  if (m.kind === "text") return Math.hypot(pt[0] - m.points[0][0], pt[1] - m.points[0][1]);
  const poly = outline(m);
  if ((m.kind === "rect" || m.kind === "cloud") && inPolygon(pt, poly)) return 0;
  let best = Infinity;
  for (let i = 0; i + 1 < poly.length; i++) best = Math.min(best, distToSegment(pt, poly[i], poly[i + 1]));
  return best;
}

/** The nearest markup within tol (a page fraction), later markups winning ties so the top one is picked. */
export function hitTest(markups: DrawingMarkup[], pt: Pt, tol = 0.01): DrawingMarkup | null {
  let best: DrawingMarkup | null = null;
  let bestD = tol;
  for (const m of markups) {
    const d = distanceToMarkup(m, pt);
    if (d <= bestD) {
      best = m;
      bestD = d;
    }
  }
  return best;
}

/** Scalloped outline for a revision cloud: one outward arc per `bump` of edge length. */
export function cloudPath(points: Pt[], bump = 0.015): string {
  if (points.length < 3) return "";
  const ring: Pt[] = [...points, points[0]];
  let d = `M ${ring[0][0]} ${ring[0][1]}`;
  for (let i = 0; i + 1 < ring.length; i++) {
    const [x0, y0] = ring[i];
    const [x1, y1] = ring[i + 1];
    const len = Math.hypot(x1 - x0, y1 - y0);
    const n = Math.max(1, Math.round(len / bump));
    const r = len / n / 2;
    for (let k = 1; k <= n; k++) {
      const x = x0 + ((x1 - x0) * k) / n;
      const y = y0 + ((y1 - y0) * k) / n;
      d += ` A ${r} ${r} 0 0 1 ${x} ${y}`;
    }
  }
  return `${d} Z`;
}

const PALETTE = ["#d1495b", "#00798c", "#edae49", "#66a182", "#30638e", "#8d6a9f", "#c97b3d", "#4c6b8a"];

/** A stable colour for an inspection type, so the same type is the same colour on every sheet. */
export function typeColor(inspectionType: string | null | undefined): string {
  if (!inspectionType) return "#555555";
  let h = 0;
  for (const ch of inspectionType) h = (h * 31 + ch.charCodeAt(0)) >>> 0;
  return PALETTE[h % PALETTE.length];
}

export function markupColor(m: Pick<DrawingMarkup, "color" | "inspectionType">): string {
  return m.color ?? typeColor(m.inspectionType);
}
