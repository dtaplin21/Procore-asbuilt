import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { 
  Layers, 
  Search, 
  Filter, 
  ZoomIn,
  ZoomOut,
  Move,
  MousePointer,
  Grid3X3,
  List,
  Eye
} from "lucide-react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Skeleton } from "@/components/ui/skeleton";
import { Badge } from "@/components/ui/badge";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import {
  Tooltip,
  TooltipContent,
  TooltipTrigger,
} from "@/components/ui/tooltip";
import { StatusBadge } from "@/components/status-badge";
import type { DrawingObject, ObjectStatus } from "@shared/schema";

const statusConfig: Record<ObjectStatus, { label: string; color: string }> = {
  not_started: { label: "Not Started", color: "bg-foreground/30" },
  pending_shop_drawing: { label: "Pending Shop Drawing", color: "bg-primary/50" },
  shop_drawing_approved: { label: "Shop Drawing Approved", color: "bg-primary" },
  installed: { label: "Installed", color: "bg-primary/70" },
  inspected: { label: "Inspected", color: "bg-primary/80" },
  as_built: { label: "As-Built Complete", color: "bg-primary" },
};

export default function Objects() {
  const [searchQuery, setSearchQuery] = useState("");
  const [statusFilter, setStatusFilter] = useState<string>("all");
  const [viewMode, setViewMode] = useState<"grid" | "list">("grid");
  const [selectedTool, setSelectedTool] = useState<"select" | "pan" | "zoom">("select");

  const { data: objects, isLoading } = useQuery<DrawingObject[]>({
    queryKey: ["/api/objects"],
  });

  const filteredObjects = objects?.filter((obj) => {
    const matchesSearch = 
      obj.objectId.toLowerCase().includes(searchQuery.toLowerCase()) ||
      obj.objectType.toLowerCase().includes(searchQuery.toLowerCase());
    
    const matchesStatus = statusFilter === "all" || obj.status === statusFilter;
    
    return matchesSearch && matchesStatus;
  });

  // Group objects by type for statistics
  const objectStats = objects?.reduce((acc, obj) => {
    if (!acc[obj.objectType]) {
      acc[obj.objectType] = { total: 0, byStatus: {} as Record<string, number> };
    }
    acc[obj.objectType].total++;
    acc[obj.objectType].byStatus[obj.status] = (acc[obj.objectType].byStatus[obj.status] || 0) + 1;
    return acc;
  }, {} as Record<string, { total: number; byStatus: Record<string, number> }>);

  return (
    <div className="p-6 space-y-6 max-w-7xl mx-auto">
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4">
        <div>
          <h1 className="text-2xl font-bold flex items-center gap-2" data-testid="text-page-title">
            <Layers className="w-6 h-6 text-muted-foreground" />
            Object Recognition
          </h1>
          <p className="text-muted-foreground">AI-recognized construction objects and their status</p>
        </div>
        <div className="flex items-center gap-2">
          <Button
            variant={viewMode === "grid" ? "default" : "outline"}
            size="icon"
            onClick={() => setViewMode("grid")}
            data-testid="button-view-grid"
          >
            <Grid3X3 className="w-4 h-4" />
          </Button>
          <Button
            variant={viewMode === "list" ? "default" : "outline"}
            size="icon"
            onClick={() => setViewMode("list")}
            data-testid="button-view-list"
          >
            <List className="w-4 h-4" />
          </Button>
        </div>
      </div>

      {/* Object Statistics */}
      {objectStats && Object.keys(objectStats).length > 0 && (
        <div className="grid grid-cols-2 md:grid-cols-4 xl:grid-cols-6 gap-4">
          {Object.entries(objectStats).slice(0, 6).map(([type, stats]) => (
            <Card key={type}>
              <CardContent className="p-4">
                <p className="text-sm font-medium text-muted-foreground capitalize">{type}s</p>
                <p className="text-2xl font-bold">{stats.total}</p>
                <div className="flex items-center gap-1 mt-2">
                  {Object.entries(stats.byStatus).slice(0, 3).map(([status, count]) => (
                    <Tooltip key={status}>
                      <TooltipTrigger asChild>
                        <div 
                          className={`h-1.5 rounded-full ${statusConfig[status as ObjectStatus]?.color || 'bg-foreground/30'}`}
                          style={{ width: `${(count / stats.total) * 100}%`, minWidth: '4px' }}
                        />
                      </TooltipTrigger>
                      <TooltipContent>
                        <p className="text-xs">{statusConfig[status as ObjectStatus]?.label}: {count}</p>
                      </TooltipContent>
                    </Tooltip>
                  ))}
                </div>
              </CardContent>
            </Card>
          ))}
        </div>
      )}

      {/* Drawing Viewer Mockup */}
      <Card>
        <CardHeader className="flex flex-row items-center justify-between gap-4 pb-4">
          <CardTitle>Drawing Viewer</CardTitle>
          <div className="flex items-center gap-1 bg-muted rounded-lg p-1">
            <Button
              variant={selectedTool === "select" ? "secondary" : "ghost"}
              size="icon"
              onClick={() => setSelectedTool("select")}
              data-testid="tool-select"
            >
              <MousePointer className="w-4 h-4" />
            </Button>
            <Button
              variant={selectedTool === "pan" ? "secondary" : "ghost"}
              size="icon"
              onClick={() => setSelectedTool("pan")}
              data-testid="tool-pan"
            >
              <Move className="w-4 h-4" />
            </Button>
            <Button
              variant={selectedTool === "zoom" ? "secondary" : "ghost"}
              size="icon"
              onClick={() => setSelectedTool("zoom")}
              data-testid="tool-zoom"
            >
              <ZoomIn className="w-4 h-4" />
            </Button>
          </div>
        </CardHeader>
        <CardContent>
          <div className="relative aspect-video bg-muted/50 rounded-lg border-2 border-dashed border-muted-foreground/20 flex items-center justify-center">
            <div className="text-center text-muted-foreground">
              <Layers className="w-12 h-12 mx-auto mb-3 opacity-50" />
              <p className="font-medium">Drawing Canvas</p>
              <p className="text-sm">Upload a construction drawing to view AI-recognized objects</p>
            </div>
            
            {/* Simulated recognized objects overlay */}
            {objects && objects.length > 0 && (
              <div className="absolute inset-0 p-4">
                {objects.slice(0, 5).map((obj, i) => (
                  <Tooltip key={obj.id}>
                    <TooltipTrigger asChild>
                      <div
                        className={`absolute w-8 h-8 rounded-full border-2 cursor-pointer transition-transform hover:scale-110 ${
                          statusConfig[obj.status]?.color || 'bg-foreground/30'
                        } bg-opacity-50 flex items-center justify-center`}
                        style={{
                          left: `${15 + (i * 18)}%`,
                          top: `${20 + (i * 12)}%`,
                        }}
                      >
                        <span className="text-xs font-bold text-white">{i + 1}</span>
                      </div>
                    </TooltipTrigger>
                    <TooltipContent>
                      <p className="font-mono text-xs">{obj.objectId}</p>
                      <p className="text-xs capitalize">{obj.objectType}</p>
                      <p className="text-xs text-muted-foreground">{statusConfig[obj.status]?.label}</p>
                    </TooltipContent>
                  </Tooltip>
                ))}
              </div>
            )}
          </div>
        </CardContent>
      </Card>

      {/* Filters */}
      <Card>
        <CardContent className="p-4">
          <div className="flex flex-col sm:flex-row gap-4">
            <div className="relative flex-1">
              <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-muted-foreground" />
              <Input
                placeholder="Search by object ID or type..."
                className="pl-9"
                value={searchQuery}
                onChange={(e) => setSearchQuery(e.target.value)}
                data-testid="input-search-objects"
              />
            </div>
            <Select value={statusFilter} onValueChange={setStatusFilter}>
              <SelectTrigger className="w-full sm:w-56" data-testid="select-status-filter">
                <Filter className="w-4 h-4 mr-2" />
                <SelectValue placeholder="Filter by status" />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="all">All Statuses</SelectItem>
                {Object.entries(statusConfig).map(([key, config]) => (
                  <SelectItem key={key} value={key}>{config.label}</SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>
        </CardContent>
      </Card>

      {/* Objects List/Grid */}
      {isLoading ? (
        <div className={viewMode === "grid" 
          ? "grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-4"
          : "space-y-2"
        }>
          {[1, 2, 3, 4, 5, 6].map((i) => (
            <Card key={i}>
              <CardContent className="p-4">
                <Skeleton className="h-5 w-32 mb-2" />
                <Skeleton className="h-4 w-24 mb-2" />
                <Skeleton className="h-6 w-28" />
              </CardContent>
            </Card>
          ))}
        </div>
      ) : filteredObjects && filteredObjects.length > 0 ? (
        viewMode === "grid" ? (
          <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-4">
            {filteredObjects.map((obj) => (
              <Card 
                key={obj.id}
                className="cursor-pointer hover-elevate active-elevate-2"
                data-testid={`card-object-${obj.id}`}
              >
                <CardContent className="p-4">
                  <div className="flex items-start justify-between gap-2 mb-3">
                    <div className={`w-3 h-3 rounded-full ${statusConfig[obj.status]?.color}`} />
                    <Badge variant="secondary" className="text-xs capitalize">
                      {obj.objectType}
                    </Badge>
                  </div>
                  
                  <h3 className="font-mono font-semibold">{obj.objectId}</h3>
                  <p className="text-sm text-muted-foreground mt-1">
                    {statusConfig[obj.status]?.label}
                  </p>
                  
                  {Object.keys(obj.metadata).length > 0 && (
                    <div className="flex flex-wrap gap-1 mt-3">
                      {Object.entries(obj.metadata).slice(0, 2).map(([key, value]) => (
                        <span 
                          key={key}
                          className="text-xs px-2 py-0.5 rounded bg-muted text-muted-foreground"
                        >
                          {key}: {value}
                        </span>
                      ))}
                    </div>
                  )}
                  
                  <div className="flex items-center gap-2 mt-4 pt-3 border-t">
                    {obj.linkedSubmittalId && (
                      <span className="text-xs text-muted-foreground">
                        Submittal linked
                      </span>
                    )}
                    {obj.linkedInspectionId && (
                      <span className="text-xs text-muted-foreground">
                        Inspection linked
                      </span>
                    )}
                    <Button variant="ghost" size="sm" className="ml-auto">
                      <Eye className="w-4 h-4 mr-1" />
                      View
                    </Button>
                  </div>
                </CardContent>
              </Card>
            ))}
          </div>
        ) : (
          <Card>
            <CardContent className="p-0">
              <div className="divide-y">
                {filteredObjects.map((obj) => (
                  <div 
                    key={obj.id}
                    className="flex items-center gap-4 p-4 hover-elevate cursor-pointer"
                    data-testid={`row-object-${obj.id}`}
                  >
                    <div className={`w-3 h-3 rounded-full ${statusConfig[obj.status]?.color}`} />
                    <div className="flex-1 min-w-0">
                      <div className="flex items-center gap-2 flex-wrap">
                        <span className="font-mono font-medium">{obj.objectId}</span>
                        <Badge variant="secondary" className="text-xs capitalize">
                          {obj.objectType}
                        </Badge>
                      </div>
                      <p className="text-sm text-muted-foreground">
                        {statusConfig[obj.status]?.label}
                      </p>
                    </div>
                    <Button variant="ghost" size="icon">
                      <Eye className="w-4 h-4" />
                    </Button>
                  </div>
                ))}
              </div>
            </CardContent>
          </Card>
        )
      ) : (
        <Card>
          <CardContent className="text-center py-12 text-muted-foreground">
            <Layers className="w-12 h-12 mx-auto mb-4 opacity-50" />
            <p className="text-lg font-medium">No objects found</p>
            <p className="text-sm">
              {searchQuery || statusFilter !== "all" 
                ? "Try adjusting your search or filters" 
                : "Upload a drawing for AI to recognize objects"}
            </p>
          </CardContent>
        </Card>
      )}

      {/* Status Legend */}
      <Card>
        <CardHeader className="pb-3">
          <CardTitle className="text-sm font-medium">Status Legend</CardTitle>
        </CardHeader>
        <CardContent>
          <div className="flex flex-wrap gap-4">
            {Object.entries(statusConfig).map(([key, config]) => (
              <div key={key} className="flex items-center gap-2">
                <div className={`w-3 h-3 rounded-full ${config.color}`} />
                <span className="text-sm text-muted-foreground">{config.label}</span>
              </div>
            ))}
          </div>
        </CardContent>
      </Card>
    </div>
  );
}
