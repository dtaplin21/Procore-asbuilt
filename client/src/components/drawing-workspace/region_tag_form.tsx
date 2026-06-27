/**
 * Label + inspection-type/location tags + save, shown after a region's
 * geometry is drawn (region_draw_canvas.tsx) or when editing an existing
 * region's tags.
 */

import { useState } from "react";

import type { DrawingRegionTags, RegionTagFormValues } from "@/lib/drawing-regions/types";

export type { DrawingRegionTags, RegionTagFormValues };

export interface RegionTagFormProps {
  initialLabel?: string;
  initialTags?: DrawingRegionTags;
  suggestedInspectionTypes?: string[];
  suggestedLocations?: string[];
  onSave: (values: RegionTagFormValues) => void;
  onCancel?: () => void;
  isSaving?: boolean;
}

function parseTagInput(value: string): string[] {
  return value
    .split(",")
    .map((s) => s.trim())
    .filter((s) => s.length > 0);
}

export function RegionTagForm({
  initialLabel = "",
  initialTags,
  suggestedInspectionTypes = [],
  suggestedLocations = [],
  onSave,
  onCancel,
  isSaving = false,
}: RegionTagFormProps) {
  const [label, setLabel] = useState(initialLabel);
  const [inspectionTypesInput, setInspectionTypesInput] = useState(
    (initialTags?.inspectionTypeTags ?? []).join(", "),
  );
  const [locationsInput, setLocationsInput] = useState(
    (initialTags?.locationTags ?? []).join(", "),
  );

  function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    const locationTags = parseTagInput(locationsInput);
    const inspectionTypeTags = parseTagInput(inspectionTypesInput);
    const resolvedLabel =
      label.trim() || locationTags[0] || inspectionTypeTags[0] || "Region";

    onSave({
      label: resolvedLabel,
      inspectionTypeTags,
      locationTags,
    });
  }

  return (
    <form
      data-testid="region-tag-form"
      onSubmit={handleSubmit}
      style={{ display: "flex", flexDirection: "column", gap: 12, maxWidth: 400 }}
    >
      <label style={{ display: "flex", flexDirection: "column", gap: 4 }}>
        <span>Label</span>
        <input
          data-testid="region-label-input"
          type="text"
          value={label}
          onChange={(e) => setLabel(e.target.value)}
          placeholder="e.g. Utility MR"
        />
      </label>

      <label style={{ display: "flex", flexDirection: "column", gap: 4 }}>
        <span>Inspection type(s)</span>
        <input
          data-testid="region-inspection-types-input"
          type="text"
          value={inspectionTypesInput}
          onChange={(e) => setInspectionTypesInput(e.target.value)}
          placeholder="e.g. Underground Fire Water Rough In, Hydrostatic Test"
          list="inspection-type-suggestions"
        />
        <datalist id="inspection-type-suggestions">
          {suggestedInspectionTypes.map((t) => (
            <option key={t} value={t} />
          ))}
        </datalist>
      </label>

      <label style={{ display: "flex", flexDirection: "column", gap: 4 }}>
        <span>Location(s)</span>
        <input
          data-testid="region-locations-input"
          type="text"
          value={locationsInput}
          onChange={(e) => setLocationsInput(e.target.value)}
          placeholder="e.g. Utility MR, Level 2"
          list="location-suggestions"
        />
        <datalist id="location-suggestions">
          {suggestedLocations.map((t) => (
            <option key={t} value={t} />
          ))}
        </datalist>
      </label>

      <div style={{ display: "flex", gap: 8 }}>
        <button type="submit" disabled={isSaving} data-testid="region-tag-form-save">
          {isSaving ? "Saving…" : "Save region"}
        </button>
        {onCancel && (
          <button type="button" onClick={onCancel} data-testid="region-tag-form-cancel">
            Cancel
          </button>
        )}
      </div>
    </form>
  );
}
