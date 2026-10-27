import { typeColor } from "../lib/markup_geometry";
import type { MarkupSummaryRow } from "../types/drawing_markup";

export interface InspectionTypeFilterProps {
  summary: MarkupSummaryRow[];
  /** Selected types. "" stands for markups with no inspection type. */
  selected: ReadonlySet<string>;
  onChange: (next: Set<string>) => void;
}

export function InspectionTypeFilter({ summary, selected, onChange }: InspectionTypeFilterProps) {
  const byType = new Map<string, { total: number; statuses: Map<string, number> }>();
  for (const row of summary) {
    const key = row.inspection_type ?? "";
    const entry = byType.get(key) ?? { total: 0, statuses: new Map<string, number>() };
    entry.total += row.count;
    entry.statuses.set(row.status ?? "No status", (entry.statuses.get(row.status ?? "No status") ?? 0) + row.count);
    byType.set(key, entry);
  }
  const toggle = (key: string) => {
    const next = new Set(selected);
    if (next.has(key)) next.delete(key); else next.add(key);
    onChange(next);
  };
  if (byType.size === 0) return <p style={{ fontSize: 13, color: "#666" }}>No markups on this page yet.</p>;
  return (
    <ul style={{ listStyle: "none", margin: 0, padding: 0 }}>
      {Array.from(byType.entries()).sort(([a], [b]) => a.localeCompare(b)).map(([key, entry]) => (
        <li key={key || "none"} style={{ marginBottom: 6 }}>
          <label style={{ display: "flex", gap: 8, alignItems: "center", fontSize: 13 }}>
            <input type="checkbox" checked={selected.has(key)} onChange={() => toggle(key)} />
            <span style={{ width: 12, height: 12, background: typeColor(key || null), display: "inline-block" }} />
            <span style={{ flex: 1 }}>{key || "No inspection type"}</span>
            <span>{entry.total}</span>
          </label>
          <div style={{ marginLeft: 28, fontSize: 11, color: "#666" }}>
            {Array.from(entry.statuses.entries()).map(([s, n]) => `${s} ${n}`).join(" · ")}
          </div>
        </li>
      ))}
    </ul>
  );
}
