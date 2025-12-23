import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { 
  ClipboardCheck, 
  Search, 
  Filter, 
  Plus, 
  Clock,
  User,
  MapPin,
  CheckCircle,
  XCircle,
  Camera,
  AlertTriangle,
  CalendarDays
} from "lucide-react";
import { Card, CardContent } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Skeleton } from "@/components/ui/skeleton";
import { Progress } from "@/components/ui/progress";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { StatusBadge } from "@/components/status-badge";
import type { Inspection } from "@shared/schema";

export default function Inspections() {
  const [searchQuery, setSearchQuery] = useState("");
  const [statusFilter, setStatusFilter] = useState<string>("all");
  const [selectedInspection, setSelectedInspection] = useState<Inspection | null>(null);

  const { data: inspections, isLoading } = useQuery<Inspection[]>({
    queryKey: ["/api/inspections"],
  });

  const filteredInspections = inspections?.filter((inspection) => {
    const matchesSearch = 
      inspection.title.toLowerCase().includes(searchQuery.toLowerCase()) ||
      inspection.number.toLowerCase().includes(searchQuery.toLowerCase()) ||
      inspection.location.toLowerCase().includes(searchQuery.toLowerCase());
    
    const matchesStatus = statusFilter === "all" || inspection.status === statusFilter;
    
    return matchesSearch && matchesStatus;
  });

  const formatDate = (date: string) => {
    return new Date(date).toLocaleDateString("en-US", {
      weekday: "short",
      month: "short",
      day: "numeric",
      hour: "2-digit",
      minute: "2-digit"
    });
  };

  const getChecklistProgress = (checklist: Inspection["checklist"]) => {
    const total = checklist.length;
    const completed = checklist.filter(item => item.passed !== null).length;
    const passed = checklist.filter(item => item.passed === true).length;
    return { total, completed, passed, percentage: total > 0 ? Math.round((completed / total) * 100) : 0 };
  };

  return (
    <div className="p-6 space-y-6 max-w-7xl mx-auto">
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4">
        <div>
          <h1 className="text-2xl font-bold flex items-center gap-2" data-testid="text-page-title">
            <ClipboardCheck className="w-6 h-6 text-muted-foreground" />
            Inspections
          </h1>
          <p className="text-muted-foreground">Field inspection tracking and AI verification</p>
        </div>
        <Button data-testid="button-new-inspection">
          <Plus className="w-4 h-4 mr-2" />
          Schedule Inspection
        </Button>
      </div>

      {/* Filters */}
      <Card>
        <CardContent className="p-4">
          <div className="flex flex-col sm:flex-row gap-4">
            <div className="relative flex-1">
              <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-muted-foreground" />
              <Input
                placeholder="Search by title, number, or location..."
                className="pl-9"
                value={searchQuery}
                onChange={(e) => setSearchQuery(e.target.value)}
                data-testid="input-search-inspections"
              />
            </div>
            <Select value={statusFilter} onValueChange={setStatusFilter}>
              <SelectTrigger className="w-full sm:w-48" data-testid="select-status-filter">
                <Filter className="w-4 h-4 mr-2" />
                <SelectValue placeholder="Filter by status" />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="all">All Statuses</SelectItem>
                <SelectItem value="scheduled">Scheduled</SelectItem>
                <SelectItem value="in_progress">In Progress</SelectItem>
                <SelectItem value="passed">Passed</SelectItem>
                <SelectItem value="failed">Failed</SelectItem>
                <SelectItem value="pending">Pending</SelectItem>
              </SelectContent>
            </Select>
          </div>
        </CardContent>
      </Card>

      {/* Inspections Grid */}
      {isLoading ? (
        <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-4">
          {[1, 2, 3, 4, 5, 6].map((i) => (
            <Card key={i}>
              <CardContent className="p-4">
                <Skeleton className="h-5 w-48 mb-2" />
                <Skeleton className="h-4 w-32 mb-4" />
                <Skeleton className="h-2 w-full mb-2" />
                <Skeleton className="h-4 w-24" />
              </CardContent>
            </Card>
          ))}
        </div>
      ) : filteredInspections && filteredInspections.length > 0 ? (
        <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-4">
          {filteredInspections.map((inspection) => {
            const progress = getChecklistProgress(inspection.checklist);
            
            return (
              <Card 
                key={inspection.id}
                className={`cursor-pointer hover-elevate active-elevate-2 transition-all ${
                  inspection.status === "failed" ? "border-foreground/30" : ""
                }`}
                onClick={() => setSelectedInspection(inspection)}
                data-testid={`card-inspection-${inspection.id}`}
              >
                <CardContent className="p-4">
                  <div className="flex items-start justify-between gap-2 mb-3">
                    <div className={`p-2 rounded-lg ${
                      inspection.status === "passed" ? "bg-primary/10" :
                      inspection.status === "failed" ? "bg-foreground/10" :
                      inspection.status === "in_progress" ? "bg-primary/10" :
                      inspection.status === "scheduled" ? "bg-primary/10" :
                      "bg-foreground/10"
                    }`}>
                      {inspection.status === "passed" ? (
                        <CheckCircle className="w-5 h-5 text-primary" />
                      ) : inspection.status === "failed" ? (
                        <XCircle className="w-5 h-5 text-foreground" />
                      ) : inspection.status === "in_progress" ? (
                        <ClipboardCheck className="w-5 h-5 text-primary" />
                      ) : (
                        <CalendarDays className="w-5 h-5 text-primary" />
                      )}
                    </div>
                    <StatusBadge status={inspection.status} />
                  </div>
                  
                  <div className="mb-3">
                    <span className="font-mono text-xs text-muted-foreground">{inspection.number}</span>
                    <h3 className="font-semibold mt-1">{inspection.title}</h3>
                    <p className="text-sm text-muted-foreground">{inspection.type}</p>
                  </div>
                  
                  <div className="space-y-2 text-sm text-muted-foreground mb-4">
                    <div className="flex items-center gap-2">
                      <MapPin className="w-3.5 h-3.5" />
                      <span className="truncate">{inspection.location}</span>
                    </div>
                    <div className="flex items-center gap-2">
                      <User className="w-3.5 h-3.5" />
                      <span>{inspection.inspector}</span>
                    </div>
                    <div className="flex items-center gap-2">
                      <Clock className="w-3.5 h-3.5" />
                      <span>{formatDate(inspection.scheduledDate)}</span>
                    </div>
                  </div>
                  
                  {inspection.checklist.length > 0 && (
                    <div className="space-y-1.5">
                      <div className="flex items-center justify-between text-xs">
                        <span className="text-muted-foreground">Checklist Progress</span>
                        <span className="font-medium">{progress.completed}/{progress.total}</span>
                      </div>
                      <Progress value={progress.percentage} className="h-1.5" />
                    </div>
                  )}
                  
                  <div className="flex items-center gap-2 mt-3 pt-3 border-t">
                    {inspection.photos.length > 0 && (
                      <span className="text-xs text-muted-foreground flex items-center gap-1">
                        <Camera className="w-3.5 h-3.5" />
                        {inspection.photos.length} photos
                      </span>
                    )}
                    {inspection.aiFindings.length > 0 && (
                      <span className="text-xs text-primary flex items-center gap-1">
                        <AlertTriangle className="w-3.5 h-3.5" />
                        {inspection.aiFindings.length} AI findings
                      </span>
                    )}
                  </div>
                </CardContent>
              </Card>
            );
          })}
        </div>
      ) : (
        <Card>
          <CardContent className="text-center py-12 text-muted-foreground">
            <ClipboardCheck className="w-12 h-12 mx-auto mb-4 opacity-50" />
            <p className="text-lg font-medium">No inspections found</p>
            <p className="text-sm">
              {searchQuery || statusFilter !== "all" 
                ? "Try adjusting your search or filters" 
                : "Schedule your first inspection to get started"}
            </p>
          </CardContent>
        </Card>
      )}

      {/* Inspection Detail Dialog */}
      <Dialog open={!!selectedInspection} onOpenChange={() => setSelectedInspection(null)}>
        <DialogContent className="max-w-2xl max-h-[80vh] overflow-y-auto">
          {selectedInspection && (
            <>
              <DialogHeader>
                <div className="flex items-start gap-3 mb-2">
                  <span className="font-mono text-sm text-muted-foreground">{selectedInspection.number}</span>
                  <StatusBadge status={selectedInspection.status} />
                </div>
                <DialogTitle className="text-xl">{selectedInspection.title}</DialogTitle>
                <DialogDescription>{selectedInspection.type}</DialogDescription>
              </DialogHeader>
              
              <div className="space-y-4 mt-4">
                <div className="grid grid-cols-2 gap-4">
                  <div>
                    <h4 className="text-sm font-medium text-muted-foreground mb-1">Location</h4>
                    <p className="text-sm flex items-center gap-2">
                      <MapPin className="w-4 h-4" />
                      {selectedInspection.location}
                    </p>
                  </div>
                  <div>
                    <h4 className="text-sm font-medium text-muted-foreground mb-1">Inspector</h4>
                    <p className="text-sm flex items-center gap-2">
                      <User className="w-4 h-4" />
                      {selectedInspection.inspector}
                    </p>
                  </div>
                  <div>
                    <h4 className="text-sm font-medium text-muted-foreground mb-1">Scheduled</h4>
                    <p className="text-sm flex items-center gap-2">
                      <Clock className="w-4 h-4" />
                      {formatDate(selectedInspection.scheduledDate)}
                    </p>
                  </div>
                  {selectedInspection.completedDate && (
                    <div>
                      <h4 className="text-sm font-medium text-muted-foreground mb-1">Completed</h4>
                      <p className="text-sm flex items-center gap-2">
                        <CheckCircle className="w-4 h-4" />
                        {formatDate(selectedInspection.completedDate)}
                      </p>
                    </div>
                  )}
                </div>
                
                {selectedInspection.checklist.length > 0 && (
                  <div>
                    <h4 className="text-sm font-medium text-muted-foreground mb-2">Checklist</h4>
                    <div className="space-y-2 max-h-48 overflow-y-auto">
                      {selectedInspection.checklist.map((item) => (
                        <div 
                          key={item.id}
                          className={`flex items-start gap-3 p-2 rounded-lg ${
                            item.passed === true ? "bg-primary/5" :
                            item.passed === false ? "bg-foreground/5" :
                            "bg-muted/30"
                          }`}
                        >
                          {item.passed === true ? (
                            <CheckCircle className="w-4 h-4 text-primary mt-0.5" />
                          ) : item.passed === false ? (
                            <XCircle className="w-4 h-4 text-foreground mt-0.5" />
                          ) : (
                            <div className="w-4 h-4 rounded-full border-2 border-muted-foreground/30 mt-0.5" />
                          )}
                          <div className="flex-1">
                            <p className="text-sm">{item.item}</p>
                            {item.notes && (
                              <p className="text-xs text-muted-foreground mt-1">{item.notes}</p>
                            )}
                          </div>
                        </div>
                      ))}
                    </div>
                  </div>
                )}
                
                {selectedInspection.aiFindings.length > 0 && (
                  <div className="p-4 rounded-lg bg-primary/5 border border-primary/20">
                    <h4 className="text-sm font-medium flex items-center gap-2 mb-2 text-primary">
                      <AlertTriangle className="w-4 h-4" />
                      AI Findings
                    </h4>
                    <ul className="space-y-1">
                      {selectedInspection.aiFindings.map((finding, i) => (
                        <li key={i} className="text-sm text-muted-foreground flex items-start gap-2">
                          <span className="text-primary">•</span>
                          {finding}
                        </li>
                      ))}
                    </ul>
                  </div>
                )}
                
                {selectedInspection.notes && (
                  <div>
                    <h4 className="text-sm font-medium text-muted-foreground mb-2">Notes</h4>
                    <p className="text-sm bg-muted/50 p-3 rounded-lg">{selectedInspection.notes}</p>
                  </div>
                )}
                
                {selectedInspection.photos.length > 0 && (
                  <div>
                    <h4 className="text-sm font-medium text-muted-foreground mb-2 flex items-center gap-2">
                      <Camera className="w-4 h-4" />
                      Photos ({selectedInspection.photos.length})
                    </h4>
                    <div className="grid grid-cols-4 gap-2">
                      {selectedInspection.photos.slice(0, 4).map((photo, i) => (
                        <div key={i} className="aspect-square rounded-lg bg-muted flex items-center justify-center">
                          <Camera className="w-6 h-6 text-muted-foreground" />
                        </div>
                      ))}
                    </div>
                  </div>
                )}
                
                <div className="flex items-center justify-end gap-2 pt-4 border-t">
                  <Button variant="outline" onClick={() => setSelectedInspection(null)}>
                    Close
                  </Button>
                  {selectedInspection.status === "scheduled" && (
                    <Button data-testid="button-start-inspection">
                      Start Inspection
                    </Button>
                  )}
                  {selectedInspection.status === "in_progress" && (
                    <Button data-testid="button-complete-inspection">
                      Complete Inspection
                    </Button>
                  )}
                </div>
              </div>
            </>
          )}
        </DialogContent>
      </Dialog>
    </div>
  );
}
