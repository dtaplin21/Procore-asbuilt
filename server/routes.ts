import type { Express } from "express";
import { createServer, type Server } from "http";
import { storage } from "./storage";

export async function registerRoutes(
  httpServer: Server,
  app: Express
): Promise<Server> {
  
  // Dashboard stats
  app.get("/api/dashboard/stats", async (req, res) => {
    try {
      const stats = await storage.getDashboardStats();
      res.json(stats);
    } catch (error) {
      res.status(500).json({ error: "Failed to fetch dashboard stats" });
    }
  });

  // Projects
  app.get("/api/projects", async (req, res) => {
    try {
      const projects = await storage.getProjects();
      res.json(projects);
    } catch (error) {
      res.status(500).json({ error: "Failed to fetch projects" });
    }
  });

  app.get("/api/projects/:id", async (req, res) => {
    try {
      const project = await storage.getProject(req.params.id);
      if (!project) {
        return res.status(404).json({ error: "Project not found" });
      }
      res.json(project);
    } catch (error) {
      res.status(500).json({ error: "Failed to fetch project" });
    }
  });

  // Submittals
  app.get("/api/submittals", async (req, res) => {
    try {
      const projectId = req.query.projectId as string | undefined;
      const limit = req.query.limit ? parseInt(req.query.limit as string) : undefined;
      let submittals = await storage.getSubmittals(projectId);
      
      // Sort by submitted date descending
      submittals.sort((a, b) => new Date(b.submittedDate).getTime() - new Date(a.submittedDate).getTime());
      
      if (limit) {
        submittals = submittals.slice(0, limit);
      }
      
      res.json(submittals);
    } catch (error) {
      res.status(500).json({ error: "Failed to fetch submittals" });
    }
  });

  app.get("/api/submittals/:id", async (req, res) => {
    try {
      const submittal = await storage.getSubmittal(req.params.id);
      if (!submittal) {
        return res.status(404).json({ error: "Submittal not found" });
      }
      res.json(submittal);
    } catch (error) {
      res.status(500).json({ error: "Failed to fetch submittal" });
    }
  });

  app.post("/api/submittals", async (req, res) => {
    try {
      const submittal = await storage.createSubmittal(req.body);
      res.status(201).json(submittal);
    } catch (error) {
      res.status(500).json({ error: "Failed to create submittal" });
    }
  });

  app.patch("/api/submittals/:id", async (req, res) => {
    try {
      const submittal = await storage.updateSubmittal(req.params.id, req.body);
      if (!submittal) {
        return res.status(404).json({ error: "Submittal not found" });
      }
      res.json(submittal);
    } catch (error) {
      res.status(500).json({ error: "Failed to update submittal" });
    }
  });

  // RFIs
  app.get("/api/rfis", async (req, res) => {
    try {
      const projectId = req.query.projectId as string | undefined;
      const limit = req.query.limit ? parseInt(req.query.limit as string) : undefined;
      let rfis = await storage.getRFIs(projectId);
      
      // Sort by created date descending
      rfis.sort((a, b) => new Date(b.createdDate).getTime() - new Date(a.createdDate).getTime());
      
      if (limit) {
        rfis = rfis.slice(0, limit);
      }
      
      res.json(rfis);
    } catch (error) {
      res.status(500).json({ error: "Failed to fetch RFIs" });
    }
  });

  app.get("/api/rfis/:id", async (req, res) => {
    try {
      const rfi = await storage.getRFI(req.params.id);
      if (!rfi) {
        return res.status(404).json({ error: "RFI not found" });
      }
      res.json(rfi);
    } catch (error) {
      res.status(500).json({ error: "Failed to fetch RFI" });
    }
  });

  app.post("/api/rfis", async (req, res) => {
    try {
      const rfi = await storage.createRFI(req.body);
      res.status(201).json(rfi);
    } catch (error) {
      res.status(500).json({ error: "Failed to create RFI" });
    }
  });

  app.patch("/api/rfis/:id", async (req, res) => {
    try {
      const rfi = await storage.updateRFI(req.params.id, req.body);
      if (!rfi) {
        return res.status(404).json({ error: "RFI not found" });
      }
      res.json(rfi);
    } catch (error) {
      res.status(500).json({ error: "Failed to update RFI" });
    }
  });

  // Inspections
  app.get("/api/inspections", async (req, res) => {
    try {
      const projectId = req.query.projectId as string | undefined;
      const limit = req.query.limit ? parseInt(req.query.limit as string) : undefined;
      let inspections = await storage.getInspections(projectId);
      
      // Sort by scheduled date descending
      inspections.sort((a, b) => new Date(b.scheduledDate).getTime() - new Date(a.scheduledDate).getTime());
      
      if (limit) {
        inspections = inspections.slice(0, limit);
      }
      
      res.json(inspections);
    } catch (error) {
      res.status(500).json({ error: "Failed to fetch inspections" });
    }
  });

  app.get("/api/inspections/:id", async (req, res) => {
    try {
      const inspection = await storage.getInspection(req.params.id);
      if (!inspection) {
        return res.status(404).json({ error: "Inspection not found" });
      }
      res.json(inspection);
    } catch (error) {
      res.status(500).json({ error: "Failed to fetch inspection" });
    }
  });

  app.post("/api/inspections", async (req, res) => {
    try {
      const inspection = await storage.createInspection(req.body);
      res.status(201).json(inspection);
    } catch (error) {
      res.status(500).json({ error: "Failed to create inspection" });
    }
  });

  app.patch("/api/inspections/:id", async (req, res) => {
    try {
      const inspection = await storage.updateInspection(req.params.id, req.body);
      if (!inspection) {
        return res.status(404).json({ error: "Inspection not found" });
      }
      res.json(inspection);
    } catch (error) {
      res.status(500).json({ error: "Failed to update inspection" });
    }
  });

  // Drawing Objects
  app.get("/api/objects", async (req, res) => {
    try {
      const projectId = req.query.projectId as string | undefined;
      const objects = await storage.getObjects(projectId);
      res.json(objects);
    } catch (error) {
      res.status(500).json({ error: "Failed to fetch objects" });
    }
  });

  app.get("/api/objects/:id", async (req, res) => {
    try {
      const obj = await storage.getObject(req.params.id);
      if (!obj) {
        return res.status(404).json({ error: "Object not found" });
      }
      res.json(obj);
    } catch (error) {
      res.status(500).json({ error: "Failed to fetch object" });
    }
  });

  // AI Insights
  app.get("/api/insights", async (req, res) => {
    try {
      const projectId = req.query.projectId as string | undefined;
      const limit = req.query.limit ? parseInt(req.query.limit as string) : undefined;
      const insights = await storage.getInsights(projectId, limit);
      res.json(insights);
    } catch (error) {
      res.status(500).json({ error: "Failed to fetch insights" });
    }
  });

  app.patch("/api/insights/:id/resolve", async (req, res) => {
    try {
      const insight = await storage.resolveInsight(req.params.id);
      if (!insight) {
        return res.status(404).json({ error: "Insight not found" });
      }
      res.json(insight);
    } catch (error) {
      res.status(500).json({ error: "Failed to resolve insight" });
    }
  });

  return httpServer;
}
