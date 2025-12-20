import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { 
  FileCheck, 
  Search, 
  Filter, 
  Plus, 
  ChevronDown,
  Clock,
  User,
  Paperclip,
  Sparkles,
  Eye
} from "lucide-react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Skeleton } from "@/components/ui/skeleton";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { StatusBadge } from "@/components/status-badge";
import { AIScoreRing } from "@/components/ai-score-ring";
import type { Submittal } from "@shared/schema";

export default function Submittals() {
  const [searchQuery, setSearchQuery] = useState("");
  const [statusFilter, setStatusFilter] = useState<string>("all");
  const [selectedSubmittal, setSelectedSubmittal] = useState<Submittal | null>(null);

  const { data: submittals, isLoading } = useQuery<Submittal[]>({
    queryKey: ["/api/submittals"],
  });

  const filteredSubmittals = submittals?.filter((submittal) => {
    const matchesSearch = 
      submittal.title.toLowerCase().includes(searchQuery.toLowerCase()) ||
      submittal.number.toLowerCase().includes(searchQuery.toLowerCase()) ||
      submittal.specSection.toLowerCase().includes(searchQuery.toLowerCase());
    
    const matchesStatus = statusFilter === "all" || submittal.status === statusFilter;
    
    return matchesSearch && matchesStatus;
  });

  const formatDate = (date: string) => {
    return new Date(date).toLocaleDateString("en-US", {
      month: "short",
      day: "numeric",
      year: "numeric"
    });
  };

  return (
    <div className="p-6 space-y-6 max-w-7xl mx-auto">
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4">
        <div>
          <h1 className="text-2xl font-bold flex items-center gap-2" data-testid="text-page-title">
            <FileCheck className="w-6 h-6 text-muted-foreground" />
            Submittals
          </h1>
          <p className="text-muted-foreground">Manage shop drawings and product data submittals</p>
        </div>
        <Button data-testid="button-new-submittal">
          <Plus className="w-4 h-4 mr-2" />
          New Submittal
        </Button>
      </div>

      {/* Filters */}
      <Card>
        <CardContent className="p-4">
          <div className="flex flex-col sm:flex-row gap-4">
            <div className="relative flex-1">
              <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-muted-foreground" />
              <Input
                placeholder="Search by title, number, or spec section..."
                className="pl-9"
                value={searchQuery}
                onChange={(e) => setSearchQuery(e.target.value)}
                data-testid="input-search-submittals"
              />
            </div>
            <Select value={statusFilter} onValueChange={setStatusFilter}>
              <SelectTrigger className="w-full sm:w-48" data-testid="select-status-filter">
                <Filter className="w-4 h-4 mr-2" />
                <SelectValue placeholder="Filter by status" />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="all">All Statuses</SelectItem>
                <SelectItem value="pending">Pending</SelectItem>
                <SelectItem value="in_review">In Review</SelectItem>
                <SelectItem value="approved">Approved</SelectItem>
                <SelectItem value="rejected">Rejected</SelectItem>
                <SelectItem value="revise_resubmit">Revise & Resubmit</SelectItem>
              </SelectContent>
            </Select>
          </div>
        </CardContent>
      </Card>

      {/* Submittals Table */}
      <Card>
        <CardContent className="p-0">
          {isLoading ? (
            <div className="p-6 space-y-4">
              {[1, 2, 3, 4, 5].map((i) => (
                <div key={i} className="flex items-center gap-4">
                  <Skeleton className="h-10 w-10 rounded-full" />
                  <div className="flex-1">
                    <Skeleton className="h-4 w-48 mb-2" />
                    <Skeleton className="h-3 w-32" />
                  </div>
                  <Skeleton className="h-6 w-20" />
                </div>
              ))}
            </div>
          ) : filteredSubmittals && filteredSubmittals.length > 0 ? (
            <div className="overflow-x-auto">
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead className="w-16">AI</TableHead>
                    <TableHead>Submittal</TableHead>
                    <TableHead>Spec Section</TableHead>
                    <TableHead>Status</TableHead>
                    <TableHead>Submitted By</TableHead>
                    <TableHead>Due Date</TableHead>
                    <TableHead className="text-right">Actions</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {filteredSubmittals.map((submittal) => (
                    <TableRow 
                      key={submittal.id}
                      className="cursor-pointer"
                      onClick={() => setSelectedSubmittal(submittal)}
                      data-testid={`row-submittal-${submittal.id}`}
                    >
                      <TableCell>
                        <AIScoreRing score={submittal.aiScore || 0} size="sm" />
                      </TableCell>
                      <TableCell>
                        <div>
                          <p className="font-medium">{submittal.title}</p>
                          <p className="text-sm text-muted-foreground font-mono">
                            {submittal.number}
                            {submittal.revisionNumber > 0 && (
                              <span className="ml-2 text-xs">Rev {submittal.revisionNumber}</span>
                            )}
                          </p>
                        </div>
                      </TableCell>
                      <TableCell>
                        <span className="font-mono text-sm">{submittal.specSection}</span>
                      </TableCell>
                      <TableCell>
                        <StatusBadge status={submittal.status} />
                      </TableCell>
                      <TableCell>
                        <div className="flex items-center gap-2">
                          <User className="w-3.5 h-3.5 text-muted-foreground" />
                          <span className="text-sm">{submittal.submittedBy}</span>
                        </div>
                      </TableCell>
                      <TableCell>
                        <div className="flex items-center gap-2">
                          <Clock className="w-3.5 h-3.5 text-muted-foreground" />
                          <span className="text-sm">{formatDate(submittal.dueDate)}</span>
                        </div>
                      </TableCell>
                      <TableCell className="text-right">
                        <div className="flex items-center justify-end gap-2">
                          {submittal.attachmentCount > 0 && (
                            <span className="text-xs text-muted-foreground flex items-center gap-1">
                              <Paperclip className="w-3.5 h-3.5" />
                              {submittal.attachmentCount}
                            </span>
                          )}
                          <Button 
                            variant="ghost" 
                            size="icon"
                            onClick={(e) => {
                              e.stopPropagation();
                              setSelectedSubmittal(submittal);
                            }}
                            data-testid={`button-view-submittal-${submittal.id}`}
                          >
                            <Eye className="w-4 h-4" />
                          </Button>
                        </div>
                      </TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            </div>
          ) : (
            <div className="text-center py-12 text-muted-foreground">
              <FileCheck className="w-12 h-12 mx-auto mb-4 opacity-50" />
              <p className="text-lg font-medium">No submittals found</p>
              <p className="text-sm">
                {searchQuery || statusFilter !== "all" 
                  ? "Try adjusting your search or filters" 
                  : "Create your first submittal to get started"}
              </p>
            </div>
          )}
        </CardContent>
      </Card>

      {/* Submittal Detail Dialog */}
      <Dialog open={!!selectedSubmittal} onOpenChange={() => setSelectedSubmittal(null)}>
        <DialogContent className="max-w-2xl">
          {selectedSubmittal && (
            <>
              <DialogHeader>
                <div className="flex items-start gap-4">
                  <AIScoreRing score={selectedSubmittal.aiScore || 0} size="lg" />
                  <div className="flex-1">
                    <DialogTitle className="text-xl">{selectedSubmittal.title}</DialogTitle>
                    <DialogDescription className="mt-1">
                      <span className="font-mono">{selectedSubmittal.number}</span>
                      {" · "}
                      {selectedSubmittal.specSection}
                      {selectedSubmittal.revisionNumber > 0 && (
                        <span className="ml-2">· Rev {selectedSubmittal.revisionNumber}</span>
                      )}
                    </DialogDescription>
                  </div>
                  <StatusBadge status={selectedSubmittal.status} />
                </div>
              </DialogHeader>
              
              <div className="space-y-4 mt-4">
                <div>
                  <h4 className="text-sm font-medium text-muted-foreground mb-1">Description</h4>
                  <p className="text-sm">{selectedSubmittal.description}</p>
                </div>
                
                <div className="grid grid-cols-2 gap-4">
                  <div>
                    <h4 className="text-sm font-medium text-muted-foreground mb-1">Submitted By</h4>
                    <p className="text-sm flex items-center gap-2">
                      <User className="w-4 h-4" />
                      {selectedSubmittal.submittedBy}
                    </p>
                  </div>
                  <div>
                    <h4 className="text-sm font-medium text-muted-foreground mb-1">Submitted Date</h4>
                    <p className="text-sm flex items-center gap-2">
                      <Clock className="w-4 h-4" />
                      {formatDate(selectedSubmittal.submittedDate)}
                    </p>
                  </div>
                </div>
                
                {selectedSubmittal.aiAnalysis && (
                  <div className="p-4 rounded-lg bg-primary/5 border border-primary/20">
                    <h4 className="text-sm font-medium flex items-center gap-2 mb-2">
                      <Sparkles className="w-4 h-4 text-primary" />
                      AI Analysis
                    </h4>
                    <p className="text-sm text-muted-foreground">{selectedSubmittal.aiAnalysis}</p>
                  </div>
                )}
                
                {selectedSubmittal.objectsCovered.length > 0 && (
                  <div>
                    <h4 className="text-sm font-medium text-muted-foreground mb-2">Objects Covered</h4>
                    <div className="flex flex-wrap gap-2">
                      {selectedSubmittal.objectsCovered.map((obj, i) => (
                        <span 
                          key={i}
                          className="text-xs font-mono px-2 py-1 rounded bg-muted text-muted-foreground"
                        >
                          {obj}
                        </span>
                      ))}
                    </div>
                  </div>
                )}
                
                <div className="flex items-center justify-end gap-2 pt-4 border-t">
                  <Button variant="outline" onClick={() => setSelectedSubmittal(null)}>
                    Close
                  </Button>
                  <Button data-testid="button-review-submittal">
                    Review Submittal
                  </Button>
                </div>
              </div>
            </>
          )}
        </DialogContent>
      </Dialog>
    </div>
  );
}
