import { useEffect, useMemo, useState } from "react";
import { useLocation, useRoute } from "wouter";
import { useQuery } from "@tanstack/react-query";

import { PerceptionSheet } from "@/components/testing/perception_sheet";
import PanZoomContainer from "@/components/drawing-workspace/pan_zoom_container";
import { fetchMasterPerception, fetchTestingMasters } from "@/lib/api/master_perception";
import { resolveFetchUrl } from "@/lib/api/http";
import {
  DEFAULT_LAYERS,
  type PerceptionLayers,
} from "@/lib/testing/perception_model";

const LAYER_LABELS: { key: keyof PerceptionLayers; label: string }[] = [
  { key: "ocr", label: "OCR text" },
  { key: "stations", label: "Station labels" },
  { key: "vocabulary", label: "Vocabulary hits" },
  { key: "ssmh", label: "SSMH" },
  { key: "pipes", label: "Pipes" },
  { key: "contours", label: "Landmark boxes" },
  { key: "controls", label: "Control points" },
  { key: "overlays", label: "Overlays" },
  { key: "regions", label: "Regions" },
];

function layersFromSearch(search: string): PerceptionLayers {
  const raw = new URLSearchParams(search).get("layers");
  if (!raw) return { ...DEFAULT_LAYERS };
  const enabled = new Set(raw.split(",").filter(Boolean));
  return {
    ocr: enabled.has("ocr"),
    stations: enabled.has("stations"),
    vocabulary: enabled.has("vocabulary"),
    ssmh: enabled.has("ssmh"),
    pipes: enabled.has("pipes"),
    contours: enabled.has("contours"),
    controls: enabled.has("controls"),
    overlays: enabled.has("overlays"),
    regions: enabled.has("regions"),
  };
}

function downloadText(filename: string, body: string, type: string) {
  const blob = new Blob([body], { type });
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = filename;
  link.click();
  URL.revokeObjectURL(url);
}

export default function MasterPerceptionPage() {
  const [, setLocation] = useLocation();
  const [, params] = useRoute("/testing/master-perception/:masterId");
  const masterId = params?.masterId ?? "";
  const search = typeof window !== "undefined" ? window.location.search : "";
  const initial = new URLSearchParams(search);
  const [query, setQuery] = useState("");
  const [page, setPage] = useState(Number(initial.get("page") || "1") || 1);
  const [runId, setRunId] = useState(initial.get("run") ?? "");
  const [layers, setLayers] = useState<PerceptionLayers>(() => layersFromSearch(search));
  const [minConfidence, setMinConfidence] = useState(0);
  const [diff, setDiff] = useState(initial.get("diff") === "1");
  const [crosshair, setCrosshair] = useState<{ x: number; y: number } | null>(null);
  const [selected, setSelected] = useState<unknown>(null);

  const masters = useQuery({
    queryKey: ["testing-masters", query],
    queryFn: () => fetchTestingMasters(query),
  });

  const perception = useQuery({
    queryKey: ["master-perception", masterId, page, runId],
    queryFn: () => fetchMasterPerception(masterId, page, runId),
    enabled: masterId !== "",
  });

  const layerKey = useMemo(
    () =>
      LAYER_LABELS.filter((item) => layers[item.key])
        .map((item) => item.key)
        .join(","),
    [layers],
  );

  useEffect(() => {
    if (!masterId) return;
    const next = new URLSearchParams();
    next.set("page", String(page));
    if (runId.trim()) next.set("run", runId.trim());
    if (diff) next.set("diff", "1");
    next.set("layers", layerKey);
    const path = `/testing/master-perception/${masterId}?${next.toString()}`;
    if (`${window.location.pathname}${window.location.search}` !== path) {
      window.history.replaceState({}, "", path);
    }
  }, [masterId, page, runId, diff, layerKey]);

  const data = perception.data;
  const imageUrl = data?.master.imageUrl ? resolveFetchUrl(data.master.imageUrl) : "";
  const stationCount = data?.ocr.filter((item) => item.isStationLabel).length ?? 0;
  const vocabCount = data?.ocr.filter((item) => item.category).length ?? 0;
  const digitizedCount = data?.pipes.filter((pipe) => pipe.source === "sheet_digitization").length ?? 0;
  const approxCount = data?.pipes.filter((pipe) => pipe.source === "survey_chain_fallback").length ?? 0;
  const unreliable = data?.registration.quality === "fail";

  return (
    <div className="flex h-full min-h-0 flex-col gap-3 p-4" data-testid="master-perception-page">
      <div className="flex flex-wrap items-end gap-3">
        <label className="flex flex-col text-xs text-muted-foreground">
          Master
          <input
            className="h-9 w-56 rounded-md border border-border bg-background px-2 text-sm text-foreground"
            value={query}
            placeholder="Drawing id or name"
            onChange={(event) => setQuery(event.target.value)}
            data-testid="perception-master-search"
          />
        </label>
        <select
          className="h-9 rounded-md border border-border bg-background px-2 text-sm"
          value={masterId}
          data-testid="perception-master-picker"
          onChange={(event) => {
            if (event.target.value) {
              setLocation(`/testing/master-perception/${event.target.value}`);
            }
          }}
        >
          <option value="">Select a master</option>
          {(masters.data?.masters ?? []).map((master) => (
            <option key={master.id} value={master.id}>
              {master.drawingNumber} · {master.id} · {master.projectName}
            </option>
          ))}
        </select>
        <label className="flex flex-col text-xs text-muted-foreground">
          Page
          <input
            className="h-9 w-20 rounded-md border border-border bg-background px-2 text-sm"
            type="number"
            min={1}
            value={page}
            onChange={(event) => setPage(Math.max(1, Number(event.target.value) || 1))}
            data-testid="perception-page"
          />
        </label>
        <label className="flex flex-col text-xs text-muted-foreground">
          Evidence run
          <input
            className="h-9 w-28 rounded-md border border-border bg-background px-2 text-sm"
            value={runId}
            onChange={(event) => setRunId(event.target.value)}
            data-testid="perception-run"
          />
        </label>
        <label className="flex items-center gap-2 text-sm">
          <input type="checkbox" checked={diff} onChange={(event) => setDiff(event.target.checked)} />
          Diff on original
        </label>
        <button
          type="button"
          className="h-9 rounded-md border border-border px-3 text-sm"
          onClick={() => {
            if (!data) return;
            downloadText(`master-${data.master.id}-perception.json`, JSON.stringify(data, null, 2), "application/json");
          }}
        >
          Download perception JSON
        </button>
        <button
          type="button"
          className="h-9 rounded-md border border-border px-3 text-sm"
          data-testid="perception-copy-link"
          onClick={() => void navigator.clipboard.writeText(window.location.href)}
        >
          Copy link
        </button>
      </div>

      {data && unreliable ? (
        <div className="rounded-md border border-red-300 bg-red-50 px-3 py-2 text-sm text-red-800" data-testid="registration-banner">
          Registration unreliable: {data.registration.pointCount < 3 ? "control-point starvation" : "control points are near-collinear"}.
        </div>
      ) : null}

      {data && data.warnings.length > 0 ? (
        <details className="rounded-md border border-amber-300 bg-amber-50 px-3 py-2 text-sm text-amber-950" data-testid="perception-warnings">
          <summary>{data.warnings.length} notes about what is not stored</summary>
          <ul className="mt-2 list-disc pl-4">
            {data.warnings.map((warning) => (
              <li key={warning}>{warning}</li>
            ))}
          </ul>
        </details>
      ) : null}

      <div className="flex flex-wrap items-center gap-x-4 gap-y-2 text-sm">
        {LAYER_LABELS.map((item) => (
          <label key={item.key} className="flex items-center gap-2">
            <input
              type="checkbox"
              checked={layers[item.key]}
              data-testid={`layer-${item.key}`}
              onChange={(event) =>
                setLayers((current) => ({ ...current, [item.key]: event.target.checked }))
              }
            />
            {item.label}
          </label>
        ))}
        <label className="flex min-w-48 items-center gap-2 text-xs text-muted-foreground">
          Minimum OCR confidence {minConfidence.toFixed(2)}
          <input
            type="range"
            min={0}
            max={1}
            step={0.05}
            value={minConfidence}
            onChange={(event) => setMinConfidence(Number(event.target.value))}
            data-testid="confidence-slider"
          />
        </label>
      </div>

      <p className="text-xs text-muted-foreground" data-testid="perception-diagnostics">
        OCR {data?.ocr.length ?? 0} · stations {stationCount} · vocabulary {vocabCount} · SSMH {data?.ssmh.length ?? 0} · pipes {digitizedCount} · survey-chain {approxCount} · contours {data?.contours.length ?? 0} · controls {data?.controlPoints.length ?? 0}
        {data ? ` · registration ${data.registration.quality}, ${data.registration.pointCount} points` : ""}
      </p>

      <div className="flex min-h-[480px] flex-1 flex-col overflow-hidden rounded-md border border-border">
          {perception.isLoading ? <p className="p-4 text-sm">Loading what the pipeline stored…</p> : null}
          {perception.error ? (
            <p className="p-4 text-sm text-red-700">{perception.error instanceof Error ? perception.error.message : "Failed to load perception"}</p>
          ) : null}
          {data ? (
            <PanZoomContainer fillViewport minScale={0.25} maxScale={24}>
              <div className="grid h-full w-full grid-cols-2 grid-rows-1 gap-3 bg-neutral-200 p-3" data-testid="perception-panes">
                <div className="flex h-full min-h-0 flex-col">
                  <p className="mb-1 text-xs font-medium">Original</p>
                  <div className="min-h-0 flex-1">
                    <PerceptionSheet
                      perception={data}
                      layers={layers}
                      minConfidence={minConfidence}
                      showImage
                      imageUrl={imageUrl}
                      diff={diff}
                      crosshair={crosshair}
                      onHover={setCrosshair}
                      onSelect={setSelected}
                    />
                  </div>
                </div>
                <div className="flex h-full min-h-0 flex-col">
                  <p className="mb-1 flex items-center justify-between text-xs font-medium">
                    Pipeline redraw
                    <button
                      type="button"
                      className="underline"
                      onClick={() => {
                        const node = document.querySelector('[data-testid="perception-redraw"]');
                        if (!node) return;
                        downloadText(
                          `master-${data.master.id}-redraw.svg`,
                          new XMLSerializer().serializeToString(node),
                          "image/svg+xml",
                        );
                      }}
                    >
                      Download SVG
                    </button>
                  </p>
                  <div className="min-h-0 flex-1">
                    <PerceptionSheet
                      perception={data}
                      layers={layers}
                      minConfidence={minConfidence}
                      showImage={false}
                      imageUrl=""
                      diff={false}
                      crosshair={crosshair}
                      onHover={setCrosshair}
                      onSelect={setSelected}
                    />
                  </div>
                </div>
              </div>
            </PanZoomContainer>
          ) : null}
      </div>
      {selected ? (
        <pre className="max-h-40 overflow-auto whitespace-pre-wrap rounded bg-muted p-2 text-xs" data-testid="perception-raw-json">
          {JSON.stringify(selected, null, 2)}
        </pre>
      ) : (
        <p className="text-xs text-muted-foreground">Click a mark to see its stored JSON.</p>
      )}
    </div>
  );
}
