/**
 * Draw tools layered over the master drawing image: drag to draw a rectangle,
 * or click-click-click + double-click to close a polygon. Emits normalized
 * geometry via onGeometryComplete — the parent (region_editor.tsx) builds the
 * createDrawingRegion payload from there.
 */

import { useState } from "react";

import {
  polygonFromPoints,
  rectFromDragPoints,
  type PointerPoint,
  type PolygonRegionDraft,
} from "@/lib/drawing-regions/geometry";
import type { DrawingRegionRectGeometry } from "@/lib/drawing-regions/types";

export type DrawTool = "rect" | "polygon";

export type RegionDrawComplete =
  | { shape: "rect"; geometry: DrawingRegionRectGeometry }
  | ({ shape: "polygon" } & PolygonRegionDraft);

export interface RegionDrawCanvasProps {
  imageUrl: string;
  pageWidth: number;
  pageHeight: number;
  tool: DrawTool;
  onGeometryComplete: (result: RegionDrawComplete) => void;
  onCancel?: () => void;
}

const MIN_DRAG_PX = 2;

export function RegionDrawCanvas({
  imageUrl,
  pageWidth,
  pageHeight,
  tool,
  onGeometryComplete,
  onCancel,
}: RegionDrawCanvasProps) {
  const [dragStart, setDragStart] = useState<PointerPoint | null>(null);
  const [dragCurrent, setDragCurrent] = useState<PointerPoint | null>(null);
  const [polygonPoints, setPolygonPoints] = useState<PointerPoint[]>([]);

  function toImagePoint(e: React.MouseEvent<HTMLDivElement>): PointerPoint {
    const rect = e.currentTarget.getBoundingClientRect();
    const fracX = (e.clientX - rect.left) / rect.width;
    const fracY = (e.clientY - rect.top) / rect.height;
    return { x: fracX * pageWidth, y: fracY * pageHeight };
  }

  function handleMouseDown(e: React.MouseEvent<HTMLDivElement>) {
    if (tool !== "rect") return;
    const point = toImagePoint(e);
    setDragStart(point);
    setDragCurrent(point);
  }

  function handleMouseMove(e: React.MouseEvent<HTMLDivElement>) {
    if (tool !== "rect" || !dragStart) return;
    setDragCurrent(toImagePoint(e));
  }

  function handleMouseUp() {
    if (tool !== "rect" || !dragStart || !dragCurrent) return;
    const widthPx = Math.abs(dragCurrent.x - dragStart.x);
    const heightPx = Math.abs(dragCurrent.y - dragStart.y);
    const geometry = rectFromDragPoints(dragStart, dragCurrent, pageWidth, pageHeight);
    setDragStart(null);
    setDragCurrent(null);
    if (widthPx > MIN_DRAG_PX && heightPx > MIN_DRAG_PX) {
      onGeometryComplete({ shape: "rect", geometry });
    }
  }

  function handleClick(e: React.MouseEvent<HTMLDivElement>) {
    if (tool !== "polygon") return;
    const point = toImagePoint(e);
    setPolygonPoints((prev) => [...prev, point]);
  }

  function handleDoubleClick() {
    if (tool !== "polygon") return;
    try {
      const draft = polygonFromPoints(polygonPoints, pageWidth, pageHeight);
      setPolygonPoints([]);
      onGeometryComplete({ shape: "polygon", ...draft });
    } catch {
      // Fewer than 3 points — ignore the double-click rather than erroring.
    }
  }

  function handleCancelClick() {
    setDragStart(null);
    setDragCurrent(null);
    setPolygonPoints([]);
    onCancel?.();
  }

  const previewRect =
    tool === "rect" && dragStart && dragCurrent
      ? rectFromDragPoints(dragStart, dragCurrent, pageWidth, pageHeight)
      : null;

  return (
    <div data-testid="region-draw-canvas" style={{ position: "relative", display: "inline-block" }}>
      <div
        data-testid="region-draw-surface"
        onMouseDown={handleMouseDown}
        onMouseMove={handleMouseMove}
        onMouseUp={handleMouseUp}
        onClick={handleClick}
        onDoubleClick={handleDoubleClick}
        style={{ position: "relative", cursor: "crosshair" }}
      >
        <img
          src={imageUrl}
          alt="Master drawing"
          style={{ display: "block", maxWidth: "100%" }}
          draggable={false}
        />

        {previewRect && (
          <div
            data-testid="region-draw-preview-rect"
            style={{
              position: "absolute",
              left: `${previewRect.x * 100}%`,
              top: `${previewRect.y * 100}%`,
              width: `${previewRect.width * 100}%`,
              height: `${previewRect.height * 100}%`,
              border: "2px dashed hsl(19 100% 50%)",
              backgroundColor: "hsla(19, 100%, 50%, 0.1)",
              pointerEvents: "none",
            }}
          />
        )}

        {tool === "polygon" && polygonPoints.length > 0 && (
          <svg
            data-testid="region-draw-preview-polygon"
            style={{
              position: "absolute",
              inset: 0,
              pointerEvents: "none",
              width: "100%",
              height: "100%",
            }}
            viewBox={`0 0 ${pageWidth} ${pageHeight}`}
            preserveAspectRatio="none"
          >
            <polyline
              points={polygonPoints.map((p) => `${p.x},${p.y}`).join(" ")}
              fill="none"
              stroke="hsl(19 100% 50%)"
              strokeWidth={3}
              strokeDasharray="6,4"
            />
            {polygonPoints.map((p, i) => (
              <circle key={i} cx={p.x} cy={p.y} r={5} fill="hsl(19 100% 50%)" />
            ))}
          </svg>
        )}
      </div>

      {(dragStart || polygonPoints.length > 0) && (
        <button type="button" onClick={handleCancelClick} data-testid="region-draw-cancel-button">
          Cancel
        </button>
      )}
    </div>
  );
}
