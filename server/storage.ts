import { randomUUID } from "crypto";
import type { 
  User, 
  InsertUser, 
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
  // Users
  getUser(id: string): Promise<User | undefined>;
  getUserByUsername(username: string): Promise<User | undefined>;
  createUser(user: InsertUser): Promise<User>;
  
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
  private users: Map<string, User>;
  private projects: Map<string, Project>;
  private submittals: Map<string, Submittal>;
  private rfis: Map<string, RFI>;
  private inspections: Map<string, Inspection>;
  private objects: Map<string, DrawingObject>;
  private insights: Map<string, AIInsight>;

  constructor() {
    this.users = new Map();
    this.projects = new Map();
    this.submittals = new Map();
    this.rfis = new Map();
    this.inspections = new Map();
    this.objects = new Map();
    this.insights = new Map();
    
    this.seedData();
  }

  private seedData() {
    // Seed Projects
    const projects: Project[] = [
      {
        id: "proj-1",
        name: "Downtown Office Tower",
        address: "123 Main Street, City",
        status: "active",
        procoreId: "12345",
        procoreSynced: true,
        lastSyncedAt: new Date().toISOString(),
        totalSubmittals: 45,
        pendingSubmittals: 12,
        totalRFIs: 28,
        openRFIs: 5,
        totalInspections: 32,
        passedInspections: 28,
      },
      {
        id: "proj-2",
        name: "Riverside Residential Complex",
        address: "456 River Road, Town",
        status: "active",
        procoreId: "12346",
        procoreSynced: true,
        lastSyncedAt: new Date().toISOString(),
        totalSubmittals: 32,
        pendingSubmittals: 8,
        totalRFIs: 15,
        openRFIs: 3,
        totalInspections: 24,
        passedInspections: 22,
      },
      {
        id: "proj-3",
        name: "Highway Infrastructure Upgrade",
        address: "Interstate 95, Section 12",
        status: "active",
        procoreId: "12347",
        procoreSynced: true,
        lastSyncedAt: new Date().toISOString(),
        totalSubmittals: 67,
        pendingSubmittals: 15,
        totalRFIs: 42,
        openRFIs: 8,
        totalInspections: 56,
        passedInspections: 48,
      },
    ];
    projects.forEach(p => this.projects.set(p.id, p));

    // Seed Submittals
    const submittals: Submittal[] = [
      {
        id: "sub-1",
        projectId: "proj-1",
        number: "SUB-001",
        title: "Structural Steel Shop Drawings - Level 5-10",
        description: "Complete structural steel fabrication drawings for levels 5 through 10 including beam connections, column details, and bracing systems.",
        status: "in_review",
        specSection: "05 12 00",
        submittedBy: "ABC Steel Fabricators",
        submittedDate: new Date(Date.now() - 3 * 24 * 60 * 60 * 1000).toISOString(),
        dueDate: new Date(Date.now() + 4 * 24 * 60 * 60 * 1000).toISOString(),
        aiScore: 87,
        aiAnalysis: "Shop drawings show good detail quality. Minor discrepancy noted in beam-to-column connection at grid line C-5. Recommend verification against design documents.",
        objectsCovered: ["BEAM-501", "BEAM-502", "COL-503", "COL-504", "BRC-505"],
        attachmentCount: 12,
        revisionNumber: 0,
      },
      {
        id: "sub-2",
        projectId: "proj-1",
        number: "SUB-002",
        title: "HVAC Ductwork - Floors 1-5",
        description: "Sheet metal ductwork shop drawings for HVAC distribution system floors 1-5.",
        status: "approved",
        specSection: "23 31 00",
        submittedBy: "Climate Control Systems",
        submittedDate: new Date(Date.now() - 10 * 24 * 60 * 60 * 1000).toISOString(),
        dueDate: new Date(Date.now() - 3 * 24 * 60 * 60 * 1000).toISOString(),
        aiScore: 95,
        aiAnalysis: "Excellent shop drawing quality. All dimensions verified against design. Fire damper locations confirmed compliant with code requirements.",
        objectsCovered: ["DUCT-101", "DUCT-102", "DUCT-103", "AHU-01"],
        attachmentCount: 8,
        revisionNumber: 1,
      },
      {
        id: "sub-3",
        projectId: "proj-1",
        number: "SUB-003",
        title: "Curtain Wall System - West Facade",
        description: "Aluminum curtain wall framing and glazing system for west building facade.",
        status: "pending",
        specSection: "08 44 00",
        submittedBy: "Glazing Solutions Inc",
        submittedDate: new Date(Date.now() - 1 * 24 * 60 * 60 * 1000).toISOString(),
        dueDate: new Date(Date.now() + 7 * 24 * 60 * 60 * 1000).toISOString(),
        aiScore: 72,
        aiAnalysis: "Analysis pending. Initial scan detected potential thermal bridging concerns at mullion intersections. Full review in progress.",
        objectsCovered: ["CW-W01", "CW-W02", "CW-W03"],
        attachmentCount: 15,
        revisionNumber: 0,
      },
      {
        id: "sub-4",
        projectId: "proj-1",
        number: "SUB-004",
        title: "Fire Sprinkler System - All Floors",
        description: "Complete fire protection sprinkler system layout and details.",
        status: "revise_resubmit",
        specSection: "21 13 00",
        submittedBy: "FireSafe Systems",
        submittedDate: new Date(Date.now() - 14 * 24 * 60 * 60 * 1000).toISOString(),
        dueDate: new Date(Date.now() - 7 * 24 * 60 * 60 * 1000).toISOString(),
        aiScore: 58,
        aiAnalysis: "Multiple issues detected: Sprinkler head spacing exceeds code maximum in open office areas. Missing coverage in electrical room. Pipe sizing calculations need verification.",
        objectsCovered: ["SPR-001", "SPR-002", "RISER-01"],
        attachmentCount: 6,
        revisionNumber: 0,
      },
      {
        id: "sub-5",
        projectId: "proj-2",
        number: "SUB-101",
        title: "Kitchen Cabinet Shop Drawings",
        description: "Custom cabinetry details for all residential units.",
        status: "approved",
        specSection: "12 32 00",
        submittedBy: "Custom Woodworks",
        submittedDate: new Date(Date.now() - 20 * 24 * 60 * 60 * 1000).toISOString(),
        dueDate: new Date(Date.now() - 10 * 24 * 60 * 60 * 1000).toISOString(),
        aiScore: 92,
        aiAnalysis: "High quality shop drawings with complete hardware specifications. All dimensions verified.",
        objectsCovered: ["CAB-A01", "CAB-A02", "CAB-B01"],
        attachmentCount: 10,
        revisionNumber: 0,
      },
    ];
    submittals.forEach(s => this.submittals.set(s.id, s));

    // Seed RFIs
    const rfis: RFI[] = [
      {
        id: "rfi-1",
        projectId: "proj-1",
        number: "RFI-001",
        subject: "Structural Column Reinforcement at Grid B-3",
        question: "The structural drawings show conflicting reinforcement details for column at grid line B-3. Drawing S-201 shows #8 bars @ 6\" spacing while S-301 shows #9 bars @ 8\" spacing. Please clarify which detail should be followed.",
        status: "open",
        priority: "high",
        createdBy: "John Smith",
        assignedTo: "Structural Engineer",
        createdDate: new Date(Date.now() - 2 * 24 * 60 * 60 * 1000).toISOString(),
        dueDate: new Date(Date.now() + 3 * 24 * 60 * 60 * 1000).toISOString(),
        drawingReferences: ["S-201", "S-301"],
        aiSuggestedResponse: "Based on analysis of similar columns in the project and typical loading conditions, S-201 detail (#8 @ 6\") appears to be correct. S-301 may have been an earlier revision. Recommend confirming with structural engineer.",
      },
      {
        id: "rfi-2",
        projectId: "proj-1",
        number: "RFI-002",
        subject: "MEP Coordination - Ductwork vs Beam Conflict",
        question: "24\" supply duct on level 7 conflicts with W21x50 beam at grid line D-5. Duct elevation shown at 12'-6\" but beam bottom is at 12'-0\". Request direction on resolution.",
        status: "answered",
        priority: "medium",
        createdBy: "Mike Johnson",
        assignedTo: "MEP Coordinator",
        createdDate: new Date(Date.now() - 5 * 24 * 60 * 60 * 1000).toISOString(),
        dueDate: new Date(Date.now() - 1 * 24 * 60 * 60 * 1000).toISOString(),
        answeredDate: new Date(Date.now() - 2 * 24 * 60 * 60 * 1000).toISOString(),
        answer: "Reroute duct around beam. Use two 45-degree elbows to offset duct by 18\" to the south. See attached sketch SK-MEP-001.",
        drawingReferences: ["M-701", "S-701"],
      },
      {
        id: "rfi-3",
        projectId: "proj-1",
        number: "RFI-003",
        subject: "Exterior Wall Waterproofing Termination",
        question: "Detail A3/A-501 does not show waterproofing membrane termination at grade level. How should membrane be terminated and protected?",
        status: "open",
        priority: "critical",
        createdBy: "Sarah Lee",
        assignedTo: "Architect",
        createdDate: new Date(Date.now() - 1 * 24 * 60 * 60 * 1000).toISOString(),
        dueDate: new Date(Date.now() + 2 * 24 * 60 * 60 * 1000).toISOString(),
        drawingReferences: ["A-501", "A-502"],
        aiSuggestedResponse: "Standard practice for this membrane type requires termination 6\" below grade with protection board and termination bar. Recommend referencing manufacturer spec sheet section 3.4.",
      },
      {
        id: "rfi-4",
        projectId: "proj-1",
        number: "RFI-004",
        subject: "Elevator Pit Depth Clarification",
        question: "Structural drawings show elevator pit at 5'-0\" deep, but elevator shop drawings require 5'-6\" minimum. Please advise.",
        status: "overdue",
        priority: "high",
        createdBy: "Tom Williams",
        assignedTo: "Structural Engineer",
        createdDate: new Date(Date.now() - 10 * 24 * 60 * 60 * 1000).toISOString(),
        dueDate: new Date(Date.now() - 3 * 24 * 60 * 60 * 1000).toISOString(),
        drawingReferences: ["S-101", "EL-001"],
      },
      {
        id: "rfi-5",
        projectId: "proj-2",
        number: "RFI-101",
        subject: "Unit Layout Modification Request",
        question: "Owner requests to relocate kitchen island in Unit 302 by 2 feet to accommodate larger refrigerator. Does this affect plumbing rough-in?",
        status: "closed",
        priority: "low",
        createdBy: "Alex Brown",
        assignedTo: "Architect",
        createdDate: new Date(Date.now() - 15 * 24 * 60 * 60 * 1000).toISOString(),
        dueDate: new Date(Date.now() - 8 * 24 * 60 * 60 * 1000).toISOString(),
        answeredDate: new Date(Date.now() - 10 * 24 * 60 * 60 * 1000).toISOString(),
        answer: "Approved. 2-foot relocation will require extension of water supply and drain lines. Issue CO for plumbing adjustment.",
        drawingReferences: ["A-302", "P-302"],
      },
    ];
    rfis.forEach(r => this.rfis.set(r.id, r));

    // Seed Inspections
    const inspections: Inspection[] = [
      {
        id: "insp-1",
        projectId: "proj-1",
        number: "INSP-001",
        title: "Structural Steel - Level 5 Connections",
        type: "Structural",
        status: "passed",
        scheduledDate: new Date(Date.now() - 2 * 24 * 60 * 60 * 1000).toISOString(),
        completedDate: new Date(Date.now() - 2 * 24 * 60 * 60 * 1000).toISOString(),
        inspector: "James Wilson",
        location: "Level 5, Grid A-D",
        checklist: [
          { id: "c1", item: "Bolt torque verification", passed: true, notes: "All bolts verified at 150 ft-lbs" },
          { id: "c2", item: "Weld visual inspection", passed: true },
          { id: "c3", item: "Connection alignment", passed: true },
          { id: "c4", item: "Fireproofing thickness", passed: true, notes: "Average 1.5\" thickness verified" },
        ],
        photos: ["photo1.jpg", "photo2.jpg", "photo3.jpg"],
        notes: "All connections meet specifications. Released for fireproofing.",
        aiFindings: [],
      },
      {
        id: "insp-2",
        projectId: "proj-1",
        number: "INSP-002",
        title: "MEP Rough-In - Level 3",
        type: "MEP",
        status: "in_progress",
        scheduledDate: new Date().toISOString(),
        inspector: "Maria Garcia",
        location: "Level 3, All Areas",
        checklist: [
          { id: "c1", item: "Electrical conduit installation", passed: true },
          { id: "c2", item: "Plumbing rough-in", passed: null },
          { id: "c3", item: "HVAC ductwork", passed: null },
          { id: "c4", item: "Fire protection piping", passed: null },
        ],
        photos: ["mep1.jpg"],
        aiFindings: ["Duct insulation appears incomplete in mechanical room - verify before closing ceiling"],
      },
      {
        id: "insp-3",
        projectId: "proj-1",
        number: "INSP-003",
        title: "Concrete Pour - Foundation Section B",
        type: "Concrete",
        status: "scheduled",
        scheduledDate: new Date(Date.now() + 1 * 24 * 60 * 60 * 1000).toISOString(),
        inspector: "David Chen",
        location: "Foundation, Section B",
        checklist: [
          { id: "c1", item: "Rebar placement verification", passed: null },
          { id: "c2", item: "Formwork alignment", passed: null },
          { id: "c3", item: "Concrete mix design approval", passed: null },
          { id: "c4", item: "Slump test", passed: null },
          { id: "c5", item: "Air entrainment test", passed: null },
        ],
        photos: [],
        aiFindings: [],
      },
      {
        id: "insp-4",
        projectId: "proj-1",
        number: "INSP-004",
        title: "Waterproofing - Below Grade Walls",
        type: "Waterproofing",
        status: "failed",
        scheduledDate: new Date(Date.now() - 5 * 24 * 60 * 60 * 1000).toISOString(),
        completedDate: new Date(Date.now() - 5 * 24 * 60 * 60 * 1000).toISOString(),
        inspector: "Robert Taylor",
        location: "Below Grade, North Wall",
        checklist: [
          { id: "c1", item: "Surface preparation", passed: true },
          { id: "c2", item: "Primer application", passed: true },
          { id: "c3", item: "Membrane thickness", passed: false, notes: "Thickness below minimum in 3 areas" },
          { id: "c4", item: "Seam integrity", passed: false, notes: "Gaps found at 2 seam locations" },
          { id: "c5", item: "Termination detail", passed: true },
        ],
        photos: ["wtrprf1.jpg", "wtrprf2.jpg", "wtrprf3.jpg", "wtrprf4.jpg"],
        notes: "Failed inspection. Membrane thickness and seam issues require remediation before re-inspection.",
        aiFindings: [
          "AI detected membrane inconsistency in photo wtrprf2.jpg - thickness varies significantly",
          "Seam overlap appears insufficient in areas shown in wtrprf3.jpg",
        ],
      },
      {
        id: "insp-5",
        projectId: "proj-2",
        number: "INSP-101",
        title: "Framing Inspection - Building A",
        type: "Framing",
        status: "passed",
        scheduledDate: new Date(Date.now() - 7 * 24 * 60 * 60 * 1000).toISOString(),
        completedDate: new Date(Date.now() - 7 * 24 * 60 * 60 * 1000).toISOString(),
        inspector: "Jennifer Adams",
        location: "Building A, Units 101-110",
        checklist: [
          { id: "c1", item: "Stud spacing", passed: true },
          { id: "c2", item: "Header sizing", passed: true },
          { id: "c3", item: "Fire blocking", passed: true },
          { id: "c4", item: "Shear wall nailing", passed: true },
        ],
        photos: ["frame1.jpg", "frame2.jpg"],
        notes: "All framing meets code requirements.",
        aiFindings: [],
      },
    ];
    inspections.forEach(i => this.inspections.set(i.id, i));

    // Seed Drawing Objects
    const objects: DrawingObject[] = [
      { id: "obj-1", projectId: "proj-1", drawingId: "S-201", objectType: "manhole", objectId: "MH-001", status: "as_built", x: 120, y: 80, width: 40, height: 40, metadata: { size: "48\"", depth: "12'-0\"" } },
      { id: "obj-2", projectId: "proj-1", drawingId: "S-201", objectType: "manhole", objectId: "MH-002", status: "inspected", x: 250, y: 120, width: 40, height: 40, metadata: { size: "48\"", depth: "10'-6\"" } },
      { id: "obj-3", projectId: "proj-1", drawingId: "S-201", objectType: "pipe", objectId: "P-001", status: "installed", x: 160, y: 85, width: 90, height: 10, linkedSubmittalId: "sub-1", metadata: { diameter: "12\"", material: "DIP" } },
      { id: "obj-4", projectId: "proj-1", drawingId: "S-201", objectType: "valve", objectId: "V-001", status: "shop_drawing_approved", x: 200, y: 80, width: 20, height: 20, metadata: { type: "Gate", size: "12\"" } },
      { id: "obj-5", projectId: "proj-1", drawingId: "M-701", objectType: "duct", objectId: "DUCT-101", status: "installed", x: 50, y: 150, width: 200, height: 30, linkedSubmittalId: "sub-2", metadata: { size: "24x12", material: "Galvanized" } },
      { id: "obj-6", projectId: "proj-1", drawingId: "M-701", objectType: "ahu", objectId: "AHU-01", status: "pending_shop_drawing", x: 280, y: 130, width: 60, height: 50, metadata: { capacity: "10,000 CFM" } },
      { id: "obj-7", projectId: "proj-1", drawingId: "A-501", objectType: "column", objectId: "COL-503", status: "inspected", x: 100, y: 100, width: 25, height: 25, linkedInspectionId: "insp-1", metadata: { size: "W14x90" } },
      { id: "obj-8", projectId: "proj-1", drawingId: "A-501", objectType: "beam", objectId: "BEAM-501", status: "shop_drawing_approved", x: 125, y: 105, width: 150, height: 15, linkedSubmittalId: "sub-1", metadata: { size: "W21x50" } },
      { id: "obj-9", projectId: "proj-2", drawingId: "A-101", objectType: "door", objectId: "DR-101", status: "not_started", x: 80, y: 200, width: 30, height: 5, metadata: { type: "Hollow Metal", size: "3'-0\" x 7'-0\"" } },
      { id: "obj-10", projectId: "proj-2", drawingId: "A-101", objectType: "window", objectId: "W-101", status: "pending_shop_drawing", x: 150, y: 180, width: 50, height: 5, metadata: { type: "Aluminum", size: "5'-0\" x 4'-0\"" } },
    ];
    objects.forEach(o => this.objects.set(o.id, o));

    // Seed AI Insights
    const insights: AIInsight[] = [
      {
        id: "ins-1",
        projectId: "proj-1",
        type: "warning",
        severity: "critical",
        title: "Fire Sprinkler Coverage Gap Detected",
        description: "AI analysis of submittal SUB-004 detected areas in open office zones where sprinkler head spacing exceeds NFPA 13 maximum requirements. Immediate review recommended before installation proceeds.",
        affectedItems: ["SPR-001", "SPR-002", "Level 5 Open Office"],
        createdAt: new Date(Date.now() - 1 * 24 * 60 * 60 * 1000).toISOString(),
        resolved: false,
        relatedSubmittalId: "sub-4",
      },
      {
        id: "ins-2",
        projectId: "proj-1",
        type: "deviation",
        severity: "medium",
        title: "Shop Drawing Dimension Variance",
        description: "Structural steel shop drawing SUB-001 shows beam connection plate thickness of 3/4\" while design documents specify 7/8\". This deviation may affect connection capacity.",
        affectedItems: ["BEAM-501", "COL-503", "Connection C-5"],
        createdAt: new Date(Date.now() - 2 * 24 * 60 * 60 * 1000).toISOString(),
        resolved: false,
        relatedSubmittalId: "sub-1",
      },
      {
        id: "ins-3",
        projectId: "proj-1",
        type: "recommendation",
        severity: "low",
        title: "Waterproofing Remediation Approach",
        description: "Based on failed inspection INSP-004 findings, AI recommends removing and reapplying membrane in failed sections rather than spot repairs to ensure long-term waterproofing integrity.",
        affectedItems: ["Below Grade North Wall", "Zones 3, 7, 12"],
        createdAt: new Date(Date.now() - 5 * 24 * 60 * 60 * 1000).toISOString(),
        resolved: false,
        relatedInspectionId: "insp-4",
      },
      {
        id: "ins-4",
        projectId: "proj-1",
        type: "compliance",
        severity: "high",
        title: "RFI Response Required - Elevator Pit",
        description: "RFI-004 regarding elevator pit depth is overdue by 3 days. This is a critical path item that may delay elevator installation. Immediate attention required.",
        affectedItems: ["RFI-004", "Elevator Pit", "S-101"],
        createdAt: new Date().toISOString(),
        resolved: false,
        relatedRFIId: "rfi-4",
      },
    ];
    insights.forEach(i => this.insights.set(i.id, i));
  }

  // User methods
  async getUser(id: string): Promise<User | undefined> {
    return this.users.get(id);
  }

  async getUserByUsername(username: string): Promise<User | undefined> {
    return Array.from(this.users.values()).find(
      (user) => user.username === username,
    );
  }

  async createUser(insertUser: InsertUser): Promise<User> {
    const id = randomUUID();
    const user: User = { ...insertUser, id };
    this.users.set(id, user);
    return user;
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
