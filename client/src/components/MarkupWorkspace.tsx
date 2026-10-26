import { useEffect, useMemo, useState } from "react";
import { VocabCategory, VOCABULARY } from "@shared/inspection_vocabulary";
import { useDrawingMarkups } from "../hooks/useDrawingMarkups";
import type { ApiOptions } from "../lib/markup_api";
import type { MarkupKind, MarkupTool, Pt } from "../types/drawing_markup";
import { InspectionTypeFilter } from "./InspectionTypeFilter";
import { MarkupLayer } from "./MarkupLayer";

export const INSPECTION_TYPES = VOCABULARY[VocabCategory.InspectionType];
export const INSPECTION_STATUSES = VOCABULARY[VocabCategory.InspectionStatus];
const TOOLS: MarkupTool[] = ["select", "polyline", "cloud", "arrow", "rect", "text"];

export interface MarkupWorkspaceProps {
  drawingId: number;
  page?: number;
  /** URL of the rendered page image. Its aspect ratio sets the size of the box the markups sit in. */
  pageImageUrl: string;
  /** Width over height of that image. Leave out to read it from the loaded image. */
  pageAspect?: number;
  api?: ApiOptions;
}

export function MarkupWorkspace({ drawingId, page = 1, pageImageUrl, pageAspect, api = {} }: MarkupWorkspaceProps) {
  const [naturalAspect, setNaturalAspect] = useState<number | null>(null);
  const { markups, summary, error, create, update, remove } = useDrawingMarkups(drawingId, page, api);
  const [tool, setTool] = useState<MarkupTool>("select");
  const [inspectionType, setInspectionType] = useState<string>(INSPECTION_TYPES[0]);
  const [status, setStatus] = useState<string>("Open");
  const [selectedTypes, setSelectedTypes] = useState<Set<string> | null>(null);
  const [selectedId, setSelectedId] = useState<number | null>(null);

  const allTypes = useMemo(() => new Set(summary.map((r) => r.inspection_type ?? "")), [summary]);
  const visible = selectedTypes ?? allTypes;
  useEffect(() => {
    if (selectedId != null && !markups.some((m) => m.id === selectedId)) setSelectedId(null);
  }, [markups, selectedId]);

  const selected = markups.find((m) => m.id === selectedId) ?? null;

  const onCreate = async (kind: MarkupKind, points: Pt[], label: string | null) => {
    const made = await create({ page, kind, points, label, inspectionType, status });
    if (made) setSelectedId(made.id);
  };

  return (
    <div style={{ display: "grid", gridTemplateColumns: "1fr 280px", gap: 16, alignItems: "start" }}>
      <div>
        <div role="toolbar" aria-label="Markup tools" style={{ display: "flex", gap: 6, marginBottom: 8, flexWrap: "wrap" }}>
          {TOOLS.map((t) => (
            <button key={t} aria-pressed={tool === t} onClick={() => setTool(t)} style={{ fontWeight: tool === t ? 700 : 400 }}>
              {t}
            </button>
          ))}
          <select aria-label="Inspection type" value={inspectionType} onChange={(e) => setInspectionType(e.target.value)}>
            {INSPECTION_TYPES.map((t) => <option key={t}>{t}</option>)}
          </select>
          <select aria-label="Status" value={status} onChange={(e) => setStatus(e.target.value)}>
            {INSPECTION_STATUSES.map((s) => <option key={s}>{s}</option>)}
          </select>
        </div>
        {error && <p role="alert" style={{ color: "#b00020" }}>{error}</p>}
        <div style={{ position: "relative", width: "100%", aspectRatio: String(pageAspect ?? naturalAspect ?? 1.4) }}>
          <img src={pageImageUrl} alt="Contract drawing" draggable={false}
            onLoad={(e) => { const { naturalWidth: w, naturalHeight: h } = e.currentTarget; if (w > 0 && h > 0) setNaturalAspect(w / h); }}
            style={{ position: "absolute", inset: 0, width: "100%", height: "100%" }} />
          <MarkupLayer markups={markups} tool={tool} visibleTypes={visible} selectedId={selectedId} onSelect={setSelectedId} onCreate={onCreate} />
        </div>
      </div>
      <aside>
        <h3 style={{ marginTop: 0 }}>Inspection types</h3>
        <InspectionTypeFilter summary={summary} selected={visible} onChange={setSelectedTypes} />
        {selected && (
          <section aria-label="Selected markup" style={{ marginTop: 16, fontSize: 13 }}>
            <strong>{selected.kind}</strong> #{selected.id} by {selected.createdBy}
            <div style={{ display: "flex", gap: 6, marginTop: 6 }}>
              <select aria-label="Selected status" value={selected.status ?? ""} onChange={(e) => update(selected.id, { status: e.target.value || null })}>
                <option value="">No status</option>
                {INSPECTION_STATUSES.map((s) => <option key={s}>{s}</option>)}
              </select>
              <button onClick={() => remove(selected.id)}>Delete</button>
            </div>
          </section>
        )}
      </aside>
    </div>
  );
}
