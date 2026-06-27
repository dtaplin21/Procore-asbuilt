/**
 * "Manage regions" mode shell — toggled on from Objects (PR4 wires the
 * toggle button into objects.tsx). Coordinates: pick a draw tool ->
 * RegionDrawCanvas captures geometry -> RegionTagForm captures tags ->
 * useCreateDrawingRegion persists it -> list of existing regions shown
 * alongside for reference/deletion.
 */

import { useState } from "react";

import {
  RegionDrawCanvas,
  type DrawTool,
  type RegionDrawComplete,
} from "@/components/drawing-workspace/region_draw_canvas";
import { RegionTagForm } from "@/components/drawing-workspace/region_tag_form";
import {
  useCreateDrawingRegion,
  useDeleteDrawingRegion,
  useDrawingRegions,
} from "@/hooks/use-drawing-regions";
import type { CreateDrawingRegionInput, RegionTagFormValues } from "@/lib/drawing-regions/types";

export interface RegionEditorProps {
  projectId: number | string;
  masterDrawingId: number | string;
  imageUrl: string;
  pageWidth: number;
  pageHeight: number;
  onClose?: () => void;
}

function toCreateInput(
  draw: RegionDrawComplete,
  values: RegionTagFormValues,
): CreateDrawingRegionInput {
  const base: CreateDrawingRegionInput = {
    label: values.label,
    geometry: draw.geometry,
    inspection_type_tags: values.inspectionTypeTags,
    location_tags: values.locationTags,
  };

  if (draw.shape === "polygon") {
    return {
      ...base,
      polygon_points: draw.polygon_points,
    };
  }

  return base;
}

export function RegionEditor({
  projectId,
  masterDrawingId,
  imageUrl,
  pageWidth,
  pageHeight,
  onClose,
}: RegionEditorProps) {
  const [tool, setTool] = useState<DrawTool>("rect");
  const [pendingDraw, setPendingDraw] = useState<RegionDrawComplete | null>(null);

  const scope = { projectId, masterDrawingId };
  const regionsQuery = useDrawingRegions(scope);
  const createRegion = useCreateDrawingRegion(scope);
  const deleteRegion = useDeleteDrawingRegion(scope);

  function handleGeometryComplete(result: RegionDrawComplete) {
    setPendingDraw(result);
  }

  function handleSaveTags(values: RegionTagFormValues) {
    if (!pendingDraw) return;
    createRegion.mutate(toCreateInput(pendingDraw, values), {
      onSuccess: () => setPendingDraw(null),
    });
  }

  function handleCancelTagForm() {
    setPendingDraw(null);
  }

  const suggestedInspectionTypes = Array.from(
    new Set((regionsQuery.data ?? []).flatMap((region) => region.inspection_type_tags)),
  );
  const suggestedLocations = Array.from(
    new Set((regionsQuery.data ?? []).flatMap((region) => region.location_tags)),
  );

  return (
    <div data-testid="region-editor" style={{ display: "flex", gap: 24 }}>
      <div style={{ display: "flex", flexDirection: "column", gap: 12 }}>
        <div style={{ display: "flex", gap: 8 }}>
          <button
            type="button"
            onClick={() => setTool("rect")}
            aria-pressed={tool === "rect"}
            data-testid="region-tool-rect"
          >
            Rectangle
          </button>
          <button
            type="button"
            onClick={() => setTool("polygon")}
            aria-pressed={tool === "polygon"}
            data-testid="region-tool-polygon"
          >
            Polygon
          </button>
          {onClose && (
            <button type="button" onClick={onClose} data-testid="region-editor-close">
              Done editing
            </button>
          )}
        </div>

        {pendingDraw ? (
          <RegionTagForm
            onSave={handleSaveTags}
            onCancel={handleCancelTagForm}
            isSaving={createRegion.isPending}
            suggestedInspectionTypes={suggestedInspectionTypes}
            suggestedLocations={suggestedLocations}
          />
        ) : (
          <RegionDrawCanvas
            imageUrl={imageUrl}
            pageWidth={pageWidth}
            pageHeight={pageHeight}
            tool={tool}
            onGeometryComplete={handleGeometryComplete}
          />
        )}

        {createRegion.isError && (
          <p role="alert" style={{ color: "#DC2626" }}>
            Could not save region: {createRegion.error.message}
          </p>
        )}
      </div>

      <div style={{ minWidth: 240 }}>
        <h3>Existing regions ({regionsQuery.data?.length ?? 0})</h3>
        {regionsQuery.isLoading && <p>Loading…</p>}
        <ul data-testid="region-editor-existing-list" style={{ listStyle: "none", padding: 0 }}>
          {regionsQuery.data?.map((region) => (
            <li
              key={region.id}
              style={{ display: "flex", justifyContent: "space-between", padding: "4px 0" }}
            >
              <span>
                {region.label}
                {" — "}
                {region.inspection_type_tags.join(", ") || "(no type)"}
                {" / "}
                {region.location_tags.join(", ") || "(no location)"}
              </span>
              <button
                type="button"
                onClick={() => deleteRegion.mutate(region.id)}
                data-testid={`region-editor-delete-${region.id}`}
              >
                Delete
              </button>
            </li>
          ))}
        </ul>
      </div>
    </div>
  );
}
