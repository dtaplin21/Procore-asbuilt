import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { 
  MessageSquareText, 
  Search, 
  Filter, 
  Plus, 
  Clock,
  User,
  AlertTriangle,
  CheckCircle,
  Sparkles,
  ExternalLink
} from "lucide-react";
import { Card, CardContent } from "@/components/ui/card";
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
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { StatusBadge } from "@/components/status-badge";
import type { RFI } from "@shared/schema";

export default function RFIs() {
  const [searchQuery, setSearchQuery] = useState("");
  const [statusFilter, setStatusFilter] = useState<string>("all");
  const [selectedRFI, setSelectedRFI] = useState<RFI | null>(null);

  const { data: rfis, isLoading } = useQuery<RFI[]>({
    queryKey: ["/api/rfis"],
  });

  const filteredRFIs = rfis?.filter((rfi) => {
    const matchesSearch = 
      rfi.subject.toLowerCase().includes(searchQuery.toLowerCase()) ||
      rfi.number.toLowerCase().includes(searchQuery.toLowerCase()) ||
      rfi.question.toLowerCase().includes(searchQuery.toLowerCase());
    
    const matchesStatus = statusFilter === "all" || rfi.status === statusFilter;
    
    return matchesSearch && matchesStatus;
  });

  const formatDate = (date: string) => {
    return new Date(date).toLocaleDateString("en-US", {
      month: "short",
      day: "numeric",
      year: "numeric"
    });
  };

  const getDaysUntilDue = (dueDate: string) => {
    const due = new Date(dueDate);
    const now = new Date();
    const diff = Math.ceil((due.getTime() - now.getTime()) / (1000 * 60 * 60 * 24));
    return diff;
  };

  return (
    <div className="p-6 space-y-6 max-w-7xl mx-auto">
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4">
        <div>
          <h1 className="text-2xl font-bold flex items-center gap-2" data-testid="text-page-title">
            <MessageSquareText className="w-6 h-6 text-muted-foreground" />
            RFIs
          </h1>
          <p className="text-muted-foreground">Request for Information management</p>
        </div>
        <Button data-testid="button-new-rfi">
          <Plus className="w-4 h-4 mr-2" />
          New RFI
        </Button>
      </div>

      {/* Filters */}
      <Card>
        <CardContent className="p-4">
          <div className="flex flex-col sm:flex-row gap-4">
            <div className="relative flex-1">
              <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-muted-foreground" />
              <Input
                placeholder="Search by subject, number, or content..."
                className="pl-9"
                value={searchQuery}
                onChange={(e) => setSearchQuery(e.target.value)}
                data-testid="input-search-rfis"
              />
            </div>
            <Select value={statusFilter} onValueChange={setStatusFilter}>
              <SelectTrigger className="w-full sm:w-48" data-testid="select-status-filter">
                <Filter className="w-4 h-4 mr-2" />
                <SelectValue placeholder="Filter by status" />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="all">All Statuses</SelectItem>
                <SelectItem value="open">Open</SelectItem>
                <SelectItem value="answered">Answered</SelectItem>
                <SelectItem value="closed">Closed</SelectItem>
                <SelectItem value="overdue">Overdue</SelectItem>
              </SelectContent>
            </Select>
          </div>
        </CardContent>
      </Card>

      {/* RFI List */}
      {isLoading ? (
        <div className="space-y-4">
          {[1, 2, 3, 4].map((i) => (
            <Card key={i}>
              <CardContent className="p-4">
                <div className="flex items-start gap-4">
                  <Skeleton className="h-10 w-10 rounded" />
                  <div className="flex-1">
                    <Skeleton className="h-5 w-48 mb-2" />
                    <Skeleton className="h-4 w-full mb-2" />
                    <Skeleton className="h-4 w-32" />
                  </div>
                </div>
              </CardContent>
            </Card>
          ))}
        </div>
      ) : filteredRFIs && filteredRFIs.length > 0 ? (
        <div className="space-y-4">
          {filteredRFIs.map((rfi) => {
            const daysUntilDue = getDaysUntilDue(rfi.dueDate);
            const isOverdue = daysUntilDue < 0 && rfi.status !== "closed" && rfi.status !== "answered";
            
            return (
              <Card 
                key={rfi.id}
                className={`cursor-pointer hover-elevate active-elevate-2 transition-all ${
                  isOverdue ? "border-foreground/30" : ""
                }`}
                onClick={() => setSelectedRFI(rfi)}
                data-testid={`card-rfi-${rfi.id}`}
              >
                <CardContent className="p-4">
                  <div className="flex items-start gap-4">
                    <div className={`p-2.5 rounded-lg ${
                      rfi.status === "overdue" || isOverdue ? "bg-foreground/10" :
                      rfi.status === "open" ? "bg-primary/10" :
                      rfi.status === "answered" ? "bg-primary/10" :
                      "bg-foreground/10"
                    }`}>
                      {rfi.status === "answered" ? (
                        <CheckCircle className={`w-5 h-5 text-primary`} />
                      ) : isOverdue || rfi.status === "overdue" ? (
                        <AlertTriangle className="w-5 h-5 text-foreground" />
                      ) : (
                        <MessageSquareText className="w-5 h-5 text-primary" />
                      )}
                    </div>
                    
                    <div className="flex-1 min-w-0">
                      <div className="flex items-center gap-2 flex-wrap mb-1">
                        <span className="font-mono text-sm text-muted-foreground">{rfi.number}</span>
                        <StatusBadge status={isOverdue ? "overdue" : rfi.status} />
                        <StatusBadge status={rfi.priority} />
                      </div>
                      
                      <h3 className="font-semibold mb-1">{rfi.subject}</h3>
                      <p className="text-sm text-muted-foreground line-clamp-2">{rfi.question}</p>
                      
                      <div className="flex items-center gap-4 mt-3 text-sm text-muted-foreground flex-wrap">
                        <span className="flex items-center gap-1">
                          <User className="w-3.5 h-3.5" />
                          {rfi.createdBy}
                        </span>
                        <span className="flex items-center gap-1">
                          <Clock className="w-3.5 h-3.5" />
                          Due {formatDate(rfi.dueDate)}
                          {daysUntilDue > 0 && daysUntilDue <= 3 && (
                            <span className="text-primary font-medium ml-1">
                              ({daysUntilDue}d left)
                            </span>
                          )}
                          {isOverdue && (
                            <span className="text-foreground font-medium ml-1">
                              ({Math.abs(daysUntilDue)}d overdue)
                            </span>
                          )}
                        </span>
                      </div>
                      
                      {rfi.drawingReferences.length > 0 && (
                        <div className="flex items-center gap-2 mt-2 flex-wrap">
                          {rfi.drawingReferences.slice(0, 3).map((ref, i) => (
                            <Badge key={i} variant="secondary" className="text-xs font-mono">
                              {ref}
                            </Badge>
                          ))}
                          {rfi.drawingReferences.length > 3 && (
                            <span className="text-xs text-muted-foreground">
                              +{rfi.drawingReferences.length - 3} more
                            </span>
                          )}
                        </div>
                      )}
                    </div>
                    
                    <div className="flex items-center gap-2">
                      {rfi.aiSuggestedResponse && (
                        <div className="p-1.5 rounded-md bg-primary/10" title="AI suggestion available">
                          <Sparkles className="w-4 h-4 text-primary" />
                        </div>
                      )}
                      <Button variant="ghost" size="icon">
                        <ExternalLink className="w-4 h-4" />
                      </Button>
                    </div>
                  </div>
                </CardContent>
              </Card>
            );
          })}
        </div>
      ) : (
        <Card>
          <CardContent className="text-center py-12 text-muted-foreground">
            <MessageSquareText className="w-12 h-12 mx-auto mb-4 opacity-50" />
            <p className="text-lg font-medium">No RFIs found</p>
            <p className="text-sm">
              {searchQuery || statusFilter !== "all" 
                ? "Try adjusting your search or filters" 
                : "Create your first RFI to get started"}
            </p>
          </CardContent>
        </Card>
      )}

      {/* RFI Detail Dialog */}
      <Dialog open={!!selectedRFI} onOpenChange={() => setSelectedRFI(null)}>
        <DialogContent className="max-w-2xl">
          {selectedRFI && (
            <>
              <DialogHeader>
                <div className="flex items-start gap-3">
                  <span className="font-mono text-sm text-muted-foreground">{selectedRFI.number}</span>
                  <StatusBadge status={selectedRFI.status} />
                  <StatusBadge status={selectedRFI.priority} />
                </div>
                <DialogTitle className="text-xl mt-2">{selectedRFI.subject}</DialogTitle>
              </DialogHeader>
              
              <div className="space-y-4 mt-4">
                <div>
                  <h4 className="text-sm font-medium text-muted-foreground mb-2">Question</h4>
                  <p className="text-sm bg-muted/50 p-3 rounded-lg">{selectedRFI.question}</p>
                </div>
                
                <div className="grid grid-cols-2 gap-4">
                  <div>
                    <h4 className="text-sm font-medium text-muted-foreground mb-1">Created By</h4>
                    <p className="text-sm flex items-center gap-2">
                      <User className="w-4 h-4" />
                      {selectedRFI.createdBy}
                    </p>
                  </div>
                  <div>
                    <h4 className="text-sm font-medium text-muted-foreground mb-1">Assigned To</h4>
                    <p className="text-sm flex items-center gap-2">
                      <User className="w-4 h-4" />
                      {selectedRFI.assignedTo}
                    </p>
                  </div>
                  <div>
                    <h4 className="text-sm font-medium text-muted-foreground mb-1">Created Date</h4>
                    <p className="text-sm flex items-center gap-2">
                      <Clock className="w-4 h-4" />
                      {formatDate(selectedRFI.createdDate)}
                    </p>
                  </div>
                  <div>
                    <h4 className="text-sm font-medium text-muted-foreground mb-1">Due Date</h4>
                    <p className="text-sm flex items-center gap-2">
                      <Clock className="w-4 h-4" />
                      {formatDate(selectedRFI.dueDate)}
                    </p>
                  </div>
                </div>
                
                {selectedRFI.answer && (
                  <div>
                    <h4 className="text-sm font-medium text-muted-foreground mb-2">Answer</h4>
                    <p className="text-sm bg-primary/5 border border-primary/20 p-3 rounded-lg">
                      {selectedRFI.answer}
                    </p>
                    {selectedRFI.answeredDate && (
                      <p className="text-xs text-muted-foreground mt-1">
                        Answered on {formatDate(selectedRFI.answeredDate)}
                      </p>
                    )}
                  </div>
                )}
                
                {selectedRFI.aiSuggestedResponse && !selectedRFI.answer && (
                  <div className="p-4 rounded-lg bg-primary/5 border border-primary/20">
                    <h4 className="text-sm font-medium flex items-center gap-2 mb-2">
                      <Sparkles className="w-4 h-4 text-primary" />
                      AI Suggested Response
                    </h4>
                    <p className="text-sm text-muted-foreground">{selectedRFI.aiSuggestedResponse}</p>
                    <Button variant="outline" size="sm" className="mt-3">
                      Use This Response
                    </Button>
                  </div>
                )}
                
                {selectedRFI.drawingReferences.length > 0 && (
                  <div>
                    <h4 className="text-sm font-medium text-muted-foreground mb-2">Drawing References</h4>
                    <div className="flex flex-wrap gap-2">
                      {selectedRFI.drawingReferences.map((ref, i) => (
                        <Badge key={i} variant="secondary" className="font-mono">
                          {ref}
                        </Badge>
                      ))}
                    </div>
                  </div>
                )}
                
                <div className="flex items-center justify-end gap-2 pt-4 border-t">
                  <Button variant="outline" onClick={() => setSelectedRFI(null)}>
                    Close
                  </Button>
                  {selectedRFI.status === "open" && (
                    <Button data-testid="button-respond-rfi">
                      Respond to RFI
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
