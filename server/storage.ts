import { randomUUID } from "crypto";
import type { 
  Project, 
  InsertProject,
  Submittal,
  InsertSubmittal,
  RFI,
  InsertRFI,
  Inspection,
  InsertInspection,
  DrawingObject,
  InsertDrawingObject,
  AIInsight,
  InsertAIInsight,
  DashboardStats
} from "@shared/schema";

export interface IStorage {
  // Projects
  getProjects(): Promise<Project[]>;
  getProject(id: string): Promise<Project | undefined>;
  
  // Submittals
  getSubmittals(projectId?: string): Promise<Submittal[]>;
  getSubmittal(id: string): Promise<Submittal | undefined>;
  createSubmittal(submittal: InsertSubmittal): Promise<Submittal>;
  updateSubmittal(id: string, updates: Partial<Submittal>): Promise<Submittal | undefined>;
  
  // RFIs
  getRFIs(projectId?: string): Promise<RFI[]>;
  getRFI(id: string): Promise<RFI | undefined>;
  createRFI(rfi: InsertRFI): Promise<RFI>;
  updateRFI(id: string, updates: Partial<RFI>): Promise<RFI | undefined>;
  
  // Inspections
  getInspections(projectId?: string): Promise<Inspection[]>;
  getInspection(id: string): Promise<Inspection | undefined>;
  createInspection(inspection: InsertInspection): Promise<Inspection>;
  updateInspection(id: string, updates: Partial<Inspection>): Promise<Inspection | undefined>;
  
  // Drawing Objects
  getObjects(projectId?: string): Promise<DrawingObject[]>;
  getObject(id: string): Promise<DrawingObject | undefined>;
  
  // AI Insights
  getInsights(projectId?: string, limit?: number): Promise<AIInsight[]>;
  resolveInsight(id: string): Promise<AIInsight | undefined>;
  
  // Dashboard
  getDashboardStats(): Promise<DashboardStats>;
}

export class MemStorage implements IStorage {
  private projects: Map<string, Project>;
  private submittals: Map<string, Submittal>;
  private rfis: Map<string, RFI>;
  private inspections: Map<string, Inspection>;
  private objects: Map<string, DrawingObject>;
  private insights: Map<string, AIInsight>;

  constructor() {
    this.projects = new Map();
    this.submittals = new Map();
    this.rfis = new Map();
    this.inspections = new Map();
    this.objects = new Map();
    this.insights = new Map();
    
    // Seed data removed - will sync from Procore instead
  }


  // Project methods
  async getProjects(): Promise<Project[]> {
    return Array.from(this.projects.values());
  }

  async getProject(id: string): Promise<Project | undefined> {
    return this.projects.get(id);
  }

  // Submittal methods
  async getSubmittals(projectId?: string): Promise<Submittal[]> {
    const all = Array.from(this.submittals.values());
    if (projectId) {
      return all.filter(s => s.projectId === projectId);
    }
    return all;
  }

  async getSubmittal(id: string): Promise<Submittal | undefined> {
    return this.submittals.get(id);
  }

  async createSubmittal(submittal: InsertSubmittal): Promise<Submittal> {
    const id = randomUUID();
    const newSubmittal: Submittal = { ...submittal, id };
    this.submittals.set(id, newSubmittal);
    return newSubmittal;
  }

  async updateSubmittal(id: string, updates: Partial<Submittal>): Promise<Submittal | undefined> {
    const existing = this.submittals.get(id);
    if (!existing) return undefined;
    const updated = { ...existing, ...updates };
    this.submittals.set(id, updated);
    return updated;
  }

  // RFI methods
  async getRFIs(projectId?: string): Promise<RFI[]> {
    const all = Array.from(this.rfis.values());
    if (projectId) {
      return all.filter(r => r.projectId === projectId);
    }
    return all;
  }

  async getRFI(id: string): Promise<RFI | undefined> {
    return this.rfis.get(id);
  }

  async createRFI(rfi: InsertRFI): Promise<RFI> {
    const id = randomUUID();
    const newRFI: RFI = { ...rfi, id };
    this.rfis.set(id, newRFI);
    return newRFI;
  }

  async updateRFI(id: string, updates: Partial<RFI>): Promise<RFI | undefined> {
    const existing = this.rfis.get(id);
    if (!existing) return undefined;
    const updated = { ...existing, ...updates };
    this.rfis.set(id, updated);
    return updated;
  }

  // Inspection methods
  async getInspections(projectId?: string): Promise<Inspection[]> {
    const all = Array.from(this.inspections.values());
    if (projectId) {
      return all.filter(i => i.projectId === projectId);
    }
    return all;
  }

  async getInspection(id: string): Promise<Inspection | undefined> {
    return this.inspections.get(id);
  }

  async createInspection(inspection: InsertInspection): Promise<Inspection> {
    const id = randomUUID();
    const newInspection: Inspection = { ...inspection, id };
    this.inspections.set(id, newInspection);
    return newInspection;
  }

  async updateInspection(id: string, updates: Partial<Inspection>): Promise<Inspection | undefined> {
    const existing = this.inspections.get(id);
    if (!existing) return undefined;
    const updated = { ...existing, ...updates };
    this.inspections.set(id, updated);
    return updated;
  }

  // Drawing Object methods
  async getObjects(projectId?: string): Promise<DrawingObject[]> {
    const all = Array.from(this.objects.values());
    if (projectId) {
      return all.filter(o => o.projectId === projectId);
    }
    return all;
  }

  async getObject(id: string): Promise<DrawingObject | undefined> {
    return this.objects.get(id);
  }

  // AI Insight methods
  async getInsights(projectId?: string, limit?: number): Promise<AIInsight[]> {
    let all = Array.from(this.insights.values());
    if (projectId) {
      all = all.filter(i => i.projectId === projectId);
    }
    all.sort((a, b) => new Date(b.createdAt).getTime() - new Date(a.createdAt).getTime());
    if (limit) {
      return all.slice(0, limit);
    }
    return all;
  }

  async resolveInsight(id: string): Promise<AIInsight | undefined> {
    const existing = this.insights.get(id);
    if (!existing) return undefined;
    const updated = { ...existing, resolved: true };
    this.insights.set(id, updated);
    return updated;
  }

  // Dashboard stats
  async getDashboardStats(): Promise<DashboardStats> {
    const projects = Array.from(this.projects.values());
    const submittals = Array.from(this.submittals.values());
    const rfis = Array.from(this.rfis.values());
    const inspections = Array.from(this.inspections.values());
    const insights = Array.from(this.insights.values());

    const today = new Date();
    today.setHours(0, 0, 0, 0);

    const approvedToday = submittals.filter(s => {
      if (s.status !== "approved") return false;
      const submittedDate = new Date(s.submittedDate);
      return submittedDate >= today;
    }).length;

    const completedInspections = inspections.filter(i => i.status === "passed" || i.status === "failed");
    const passedInspections = inspections.filter(i => i.status === "passed");
    const passRate = completedInspections.length > 0 
      ? Math.round((passedInspections.length / completedInspections.length) * 100) 
      : 100;

    const criticalInsights = insights.filter(i => !i.resolved && i.severity === "critical");

    return {
      totalProjects: projects.length,
      activeProjects: projects.filter(p => p.status === "active").length,
      totalSubmittals: submittals.length,
      pendingReview: submittals.filter(s => s.status === "pending" || s.status === "in_review").length,
      approvedToday,
      openRFIs: rfis.filter(r => r.status === "open").length,
      overdueRFIs: rfis.filter(r => r.status === "overdue").length,
      scheduledInspections: inspections.filter(i => i.status === "scheduled").length,
      passRate,
      aiInsightsCount: insights.filter(i => !i.resolved).length,
      criticalAlerts: criticalInsights.length,
    };
  }
}

export const storage = new MemStorage();
