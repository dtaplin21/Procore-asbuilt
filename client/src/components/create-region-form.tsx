import { useState } from "react";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { MapPin } from "lucide-react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { useToast } from "@/hooks/use-toast";
import type {
  ProjectResponse,
  DrawingResponse,
  DrawingRegionCreate,
  DrawingRegionGeometry,
  DrawingRegionResponse,
} from "@shared/schema";

interface CreateRegionFormProps {
  projectId: string | null;
  masterDrawingId: string | null;
  projects: ProjectResponse[];
  drawings: DrawingResponse[];
  projectsLoading?: boolean;
  drawingsLoading?: boolean;
  onProjectChange: (id: string | null) => void;
  onDrawingChange: (id: string | null) => void;
}

type GeometryType = "rect" | "polygon";

async function createRegion(
  projectId: string,
  masterDrawingId: string,
  body: DrawingRegionCreate
): Promise<DrawingRegionResponse> {
  const res = await fetch(
    `/api/projects/${projectId}/drawings/${masterDrawingId}/regions`,
    {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      credentials: "include",
      body: JSON.stringify(body),
    }
  );
  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw new Error(err.detail || res.statusText || "Failed to create region");
  }
  return res.json();
}

function parsePolygonPoints(input: string): [number, number][] | null {
  const trimmed = input.trim();
  if (!trimmed) return null;
  try {
    const parsed = JSON.parse(trimmed);
    if (!Array.isArray(parsed)) return null;
    for (const p of parsed) {
      if (!Array.isArray(p) || p.length < 2) return null;
      if (typeof p[0] !== "number" || typeof p[1] !== "number") return null;
    }
    return parsed as [number, number][];
  } catch {
    return null;
  }
}

function clamp01(n: number): number {
  return Math.max(0, Math.min(1, Number(n) || 0));
}

export function CreateRegionForm({
  projectId,
  masterDrawingId,
  projects,
  drawings,
  projectsLoading,
  drawingsLoading,
  onProjectChange,
  onDrawingChange,
}: CreateRegionFormProps) {
  const { toast } = useToast();
  const queryClient = useQueryClient();
  const [label, setLabel] = useState("");
  const [page, setPage] = useState(1);
  const [geometryType, setGeometryType] = useState<GeometryType>("rect");
  const [rect, setRect] = useState({ x: 0.25, y: 0.4, width: 0.1, height: 0.2 });
  const [polygonPoints, setPolygonPoints] = useState(
    "[[0.1,0.2],[0.2,0.25],[0.18,0.35]]"
  );

  const createMutation = useMutation<DrawingRegionResponse, Error, DrawingRegionCreate>({
    mutationFn: (body) =>
      createRegion(
        projectId!,
        masterDrawingId!,
        body
      ),
    onSuccess: (region: DrawingRegionResponse) => {
      queryClient.invalidateQueries({
        queryKey: [
          `/api/projects/${projectId}/drawings/${masterDrawingId}/regions`,
        ],
      });
      setLabel("");
      toast({ title: "Region created" });
    },
    onError: (err: Error) => {
      toast({ title: "Failed to create region", description: err.message, variant: "destructive" });
    },
  });

  const canSubmit =
    projectId &&
    masterDrawingId &&
    label.trim() &&
    page >= 1 &&
    (geometryType === "rect" || parsePolygonPoints(polygonPoints) !== null);

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    if (!canSubmit) return;

    let geometry: DrawingRegionGeometry;
    if (geometryType === "rect") {
      geometry = {
        type: "rect",
        x: clamp01(rect.x),
        y: clamp01(rect.y),
        width: clamp01(rect.width),
        height: clamp01(rect.height),
      };
    } else {
      const points = parsePolygonPoints(polygonPoints);
      if (!points || points.length < 3) {
        toast({
          title: "Invalid polygon",
          description: "Need at least 3 points",
          variant: "destructive",
        });
        return;
      }
      geometry = { type: "polygon", points };
    }

    createMutation.mutate({ label: label.trim(), page, geometry });
  };

  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex items-center gap-2">
          <MapPin className="w-5 h-5" />
          Create Region (Manual)
        </CardTitle>
      </CardHeader>
      <CardContent>
        <form onSubmit={handleSubmit} className="space-y-4">
          <div className="grid gap-2">
            <Label htmlFor="region-project">Project</Label>
            <Select
              value={projectId ?? ""}
              onValueChange={(v) => {
                onProjectChange(v || null);
                onDrawingChange(null);
              }}
              disabled={projectsLoading}
            >
              <SelectTrigger id="region-project">
                <SelectValue placeholder="Select project" />
              </SelectTrigger>
              <SelectContent>
                {projects.map((p) => (
                  <SelectItem key={String(p.id)} value={String(p.id)}>
                    {p.name}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>

          <div className="grid gap-2">
            <Label htmlFor="region-drawing">Master Drawing</Label>
            <Select
              value={masterDrawingId ?? ""}
              onValueChange={(v) => onDrawingChange(v || null)}
              disabled={!projectId || drawingsLoading}
            >
              <SelectTrigger id="region-drawing">
                <SelectValue placeholder="Select drawing" />
              </SelectTrigger>
              <SelectContent>
                {drawings.map((d) => (
                  <SelectItem key={d.id} value={String(d.id)}>
                    {d.name || `Drawing ${d.id}`}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>

          <div className="grid gap-2">
            <Label htmlFor="region-label">Label</Label>
            <Input
              id="region-label"
              value={label}
              onChange={(e) => setLabel(e.target.value)}
              placeholder="e.g. Level 1 - East Wing"
            />
          </div>

          <div className="grid gap-2">
            <Label htmlFor="region-page">Page</Label>
            <Input
              id="region-page"
              type="number"
              min={1}
              value={page}
              onChange={(e) => setPage(parseInt(e.target.value, 10) || 1)}
            />
          </div>

          <div className="grid gap-2">
            <Label>Geometry Type</Label>
            <Select
              value={geometryType}
              onValueChange={(v) => setGeometryType(v as GeometryType)}
            >
              <SelectTrigger>
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="rect">Rectangle</SelectItem>
                <SelectItem value="polygon">Polygon</SelectItem>
              </SelectContent>
            </Select>
          </div>

          {geometryType === "rect" && (
            <div className="grid grid-cols-2 gap-3">
              <div className="grid gap-2">
                <Label htmlFor="rect-x">x (0-1)</Label>
                <Input
                  id="rect-x"
                  type="number"
                  min={0}
                  max={1}
                  step={0.01}
                  value={rect.x}
                  onChange={(e) =>
                    setRect((r) => ({ ...r, x: parseFloat(e.target.value) || 0 }))
                  }
                />
              </div>
              <div className="grid gap-2">
                <Label htmlFor="rect-y">y (0-1)</Label>
                <Input
                  id="rect-y"
                  type="number"
                  min={0}
                  max={1}
                  step={0.01}
                  value={rect.y}
                  onChange={(e) =>
                    setRect((r) => ({ ...r, y: parseFloat(e.target.value) || 0 }))
                  }
                />
              </div>
              <div className="grid gap-2">
                <Label htmlFor="rect-width">width (0-1)</Label>
                <Input
                  id="rect-width"
                  type="number"
                  min={0}
                  max={1}
                  step={0.01}
                  value={rect.width}
                  onChange={(e) =>
                    setRect((r) => ({
                      ...r,
                      width: parseFloat(e.target.value) || 0,
                    }))
                  }
                />
              </div>
              <div className="grid gap-2">
                <Label htmlFor="rect-height">height (0-1)</Label>
                <Input
                  id="rect-height"
                  type="number"
                  min={0}
                  max={1}
                  step={0.01}
                  value={rect.height}
                  onChange={(e) =>
                    setRect((r) => ({
                      ...r,
                      height: parseFloat(e.target.value) || 0,
                    }))
                  }
                />
              </div>
            </div>
          )}

          {geometryType === "polygon" && (
            <div className="grid gap-2">
              <Label htmlFor="polygon-points">Points (JSON array)</Label>
              <Textarea
                id="polygon-points"
                placeholder="[[0.1,0.2],[0.2,0.25],[0.18,0.35]]"
                value={polygonPoints}
                onChange={(e) => setPolygonPoints(e.target.value)}
                rows={3}
                className="font-mono text-sm"
              />
              <p className="text-xs text-muted-foreground">
                Paste normalized points as JSON, e.g. [[0.1,0.2],[0.2,0.25],[0.18,0.35]]
              </p>
            </div>
          )}

          <Button
            type="submit"
            disabled={!canSubmit || createMutation.isPending}
          >
            {createMutation.isPending ? "Creating…" : "Create Region"}
          </Button>
        </form>
      </CardContent>
    </Card>
  );
}
