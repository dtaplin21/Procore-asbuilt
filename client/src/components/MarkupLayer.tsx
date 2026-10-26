import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { cloudPath, hitTest, markupColor, outline, toFraction } from "../lib/markup_geometry";
import type { DrawingMarkup, MarkupKind, MarkupTool, Pt } from "../types/drawing_markup";

export interface MarkupLayerProps {
  markups: DrawingMarkup[];
  tool: MarkupTool;
  /** Types to draw. null shows every markup. */
  visibleTypes?: ReadonlySet<string> | null;
  selectedId?: number | null;
  onSelect?: (id: number | null) => void;
  onCreate?: (kind: MarkupKind, points: Pt[], label: string | null) => void;
  /** Called for the text tool. Return null to cancel. */
  askLabel?: () => string | null;
}

const MIN_DRAG = 0.003;

/** Absolutely positioned layer. Put it inside the same box as the rendered page image, sized 100% by 100%. */
export function MarkupLayer({ markups, tool, visibleTypes = null, selectedId = null, onSelect, onCreate, askLabel }: MarkupLayerProps) {
  const ref = useRef<HTMLDivElement>(null);
  const [draft, setDraft] = useState<Pt[]>([]);
  const [hover, setHover] = useState<Pt | null>(null);
  const dragStart = useRef<Pt | null>(null);
  const multi = tool === "polyline" || tool === "cloud";

  const shown = useMemo(
    () => markups.filter((m) => visibleTypes == null || (m.inspectionType != null && visibleTypes.has(m.inspectionType)) || (m.inspectionType == null && visibleTypes.has(""))),
    [markups, visibleTypes],
  );

  const at = (e: { clientX: number; clientY: number }): Pt => toFraction(ref.current!.getBoundingClientRect(), e.clientX, e.clientY);

  const finish = useCallback(() => {
    if (multi && draft.length >= (tool === "cloud" ? 3 : 2)) onCreate?.(tool as MarkupKind, draft, null);
    setDraft([]);
    setHover(null);
  }, [draft, multi, onCreate, tool]);

  useEffect(() => {
    setDraft([]);
    setHover(null);
    dragStart.current = null;
  }, [tool]);

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") { setDraft([]); setHover(null); dragStart.current = null; }
      if (e.key === "Enter") finish();
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [finish]);

  const onPointerDown = (e: React.PointerEvent) => {
    const p = at(e);
    if (tool === "select") {
      onSelect?.(hitTest(shown, p)?.id ?? null);
    } else if (tool === "arrow" || tool === "rect") {
      dragStart.current = p;
      setHover(p);
    } else if (tool === "text") {
      const label = (askLabel ?? (() => window.prompt("Note text")))();
      if (label && label.trim()) onCreate?.("text", [p], label.trim());
    } else if (multi) {
      setDraft((d) => [...d, p]);
    }
  };
  const onPointerMove = (e: React.PointerEvent) => {
    if (tool !== "select" && tool !== "text") setHover(at(e));
  };
  const onPointerUp = (e: React.PointerEvent) => {
    const start = dragStart.current;
    dragStart.current = null;
    if (!start || (tool !== "arrow" && tool !== "rect")) return;
    const end = at(e);
    if (Math.hypot(end[0] - start[0], end[1] - start[1]) < MIN_DRAG) { setHover(null); return; }
    onCreate?.(tool, [start, end], null);
    setHover(null);
  };

  const preview: Pt[] = useMemo(() => {
    if (dragStart.current && hover && (tool === "arrow" || tool === "rect")) return [dragStart.current, hover];
    if (multi && draft.length) return hover ? [...draft, hover] : draft;
    return [];
  }, [draft, hover, multi, tool]);

  return (
    <div
      ref={ref}
      data-testid="markup-layer"
      style={{ position: "absolute", inset: 0, touchAction: "none", cursor: tool === "select" ? "default" : "crosshair" }}
      onPointerDown={onPointerDown}
      onPointerMove={onPointerMove}
      onPointerUp={onPointerUp}
      onDoubleClick={() => finish()}
    >
      <svg viewBox="0 0 1 1" preserveAspectRatio="none" width="100%" height="100%" style={{ position: "absolute", inset: 0, overflow: "visible" }}>
        <defs>
          {shown.filter((m) => m.kind === "arrow").map((m) => (
            <marker key={m.id} id={`arrowhead-${m.id}`} viewBox="0 0 10 10" refX="9" refY="5" markerWidth="8" markerHeight="8" orient="auto-start-reverse">
              <path d="M 0 0 L 10 5 L 0 10 z" fill={markupColor(m)} />
            </marker>
          ))}
        </defs>
        {shown.filter((m) => m.kind !== "text").map((m) => {
          const color = markupColor(m);
          const common = {
            stroke: color, fill: "none", strokeWidth: m.id === selectedId ? 4 : 2, vectorEffect: "non-scaling-stroke" as const,
            strokeLinejoin: "round" as const, strokeLinecap: "round" as const,
          };
          const key = `m-${m.id}`;
          if (m.kind === "cloud") return <path key={key} d={cloudPath(m.points)} {...common} fill={`${color.slice(0, 7)}22`} />;
          if (m.kind === "rect") return <polygon key={key} points={outline(m).map((p) => p.join(",")).join(" ")} {...common} fill={`${color.slice(0, 7)}22`} />;
          if (m.kind === "arrow") return <polyline key={key} points={m.points.map((p) => p.join(",")).join(" ")} {...common} markerEnd={`url(#arrowhead-${m.id})`} />;
          return <polyline key={key} points={m.points.map((p) => p.join(",")).join(" ")} {...common} />;
        })}
        {preview.length >= 2 && (
          <polyline
            data-testid="draft"
            points={(tool === "rect" ? outline({ kind: "rect", points: preview.slice(0, 2) }) : preview).map((p) => p.join(",")).join(" ")}
            stroke="#1a73e8" fill="none" strokeWidth={2} strokeDasharray="6 4" vectorEffect="non-scaling-stroke"
          />
        )}
      </svg>
      {shown.filter((m) => m.kind === "text").map((m) => (
        <div
          key={`t-${m.id}`}
          style={{
            position: "absolute", left: `${m.points[0][0] * 100}%`, top: `${m.points[0][1] * 100}%`, transform: "translate(0, -100%)",
            background: "#fffbe6", border: `2px solid ${markupColor(m)}`, padding: "2px 6px", fontSize: 12, maxWidth: 240,
            outline: m.id === selectedId ? "2px solid #1a73e8" : "none", pointerEvents: "none",
          }}
        >
          {m.label}
        </div>
      ))}
    </div>
  );
}
