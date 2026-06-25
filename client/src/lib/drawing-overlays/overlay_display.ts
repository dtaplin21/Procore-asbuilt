import type { DrawingOverlay } from "@shared/schema";

function readWireLabel(overlay: DrawingOverlay): string | null {
  const wire = overlay as DrawingOverlay & { label?: string | null };
  if (typeof wire.label === "string" && wire.label.trim()) {
    return wire.label.trim();
  }
  return null;
}

function readTagsJson(overlay: DrawingOverlay): Record<string, unknown> | null {
  const wire = overlay as DrawingOverlay & {
    tagsJson?: Record<string, unknown> | null;
    tags_json?: Record<string, unknown> | null;
  };
  const tags = wire.tagsJson ?? wire.tags_json;
  return tags && typeof tags === "object" ? tags : null;
}

function readInspectionDate(overlay: DrawingOverlay): string | null {
  const wire = overlay as DrawingOverlay & {
    inspectionDate?: string | null;
    inspection_date?: string | null;
  };
  const value = wire.inspectionDate ?? wire.inspection_date;
  return typeof value === "string" && value.trim() ? value.trim() : null;
}

function stringList(value: unknown): string[] {
  if (!Array.isArray(value)) return [];
  return value.filter((item): item is string => typeof item === "string" && item.trim().length > 0);
}

/** Human-readable tag chips from pipeline tags_json. */
export function formatOverlayTagSummary(overlay: DrawingOverlay): string {
  const tags = readTagsJson(overlay);
  if (!tags) return "";

  const parts: string[] = [];
  parts.push(...stringList(tags.inspectionStatuses ?? tags.inspection_statuses));
  parts.push(...stringList(tags.inspectionTypes ?? tags.inspection_types));
  parts.push(...stringList(tags.locations));
  parts.push(...stringList(tags.fieldConditions ?? tags.field_conditions));
  parts.push(...stringList(tags.actions));

  return [...new Set(parts)].slice(0, 4).join(" · ");
}

export function formatOverlayListItem(overlay: DrawingOverlay): {
  title: string;
  subtitle: string;
  status: string;
} {
  const label = readWireLabel(overlay);
  const tags = formatOverlayTagSummary(overlay);
  const inspectionDate = readInspectionDate(overlay);
  const uploaded = overlay.created_at
    ? new Date(overlay.created_at).toLocaleString(undefined, {
        month: "short",
        day: "numeric",
        hour: "2-digit",
        minute: "2-digit",
      })
    : null;

  const subtitleParts = [
    tags,
    inspectionDate ? `Inspected ${inspectionDate}` : null,
    uploaded ? `Uploaded ${uploaded}` : null,
  ].filter(Boolean);

  return {
    title: label ?? `Overlay #${overlay.id}`,
    subtitle: subtitleParts.join(" · ") || overlay.status,
    status: overlay.status,
  };
}
