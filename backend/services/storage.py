from sqlalchemy.orm import Session
from models.database import Project, Submittal, RFI, Inspection, DrawingObject, AIInsight
from models.schemas import DashboardStats
from datetime import datetime, date
from typing import Optional, List
import uuid

class StorageService:
    def __init__(self, db: Session):
        self.db = db
    
    # Projects
    def get_projects(self) -> List[Project]:
        return self.db.query(Project).all()
    
    def get_project(self, project_id: str) -> Optional[Project]:
        return self.db.query(Project).filter(Project.id == project_id).first()
    
    # Submittals
    def get_submittals(self, project_id: Optional[str] = None) -> List[Submittal]:
        query = self.db.query(Submittal)
        if project_id:
            query = query.filter(Submittal.project_id == project_id)
        return query.order_by(Submittal.submitted_date.desc()).all()
    
    def get_submittal(self, submittal_id: str) -> Optional[Submittal]:
        return self.db.query(Submittal).filter(Submittal.id == submittal_id).first()
    
    def create_submittal(self, submittal_data: dict) -> Submittal:
        submittal = Submittal(id=str(uuid.uuid4()), **submittal_data)
        self.db.add(submittal)
        self.db.commit()
        self.db.refresh(submittal)
        return submittal
    
    def update_submittal(self, submittal_id: str, updates: dict) -> Optional[Submittal]:
        submittal = self.get_submittal(submittal_id)
        if not submittal:
            return None
        for key, value in updates.items():
            setattr(submittal, key, value)
        self.db.commit()
        self.db.refresh(submittal)
        return submittal
    
    # RFIs
    def get_rfis(self, project_id: Optional[str] = None) -> List[RFI]:
        query = self.db.query(RFI)
        if project_id:
            query = query.filter(RFI.project_id == project_id)
        return query.order_by(RFI.created_date.desc()).all()
    
    def get_rfi(self, rfi_id: str) -> Optional[RFI]:
        return self.db.query(RFI).filter(RFI.id == rfi_id).first()
    
    def create_rfi(self, rfi_data: dict) -> RFI:
        rfi = RFI(id=str(uuid.uuid4()), **rfi_data)
        self.db.add(rfi)
        self.db.commit()
        self.db.refresh(rfi)
        return rfi
    
    def update_rfi(self, rfi_id: str, updates: dict) -> Optional[RFI]:
        rfi = self.get_rfi(rfi_id)
        if not rfi:
            return None
        for key, value in updates.items():
            setattr(rfi, key, value)
        self.db.commit()
        self.db.refresh(rfi)
        return rfi
    
    # Inspections
    def get_inspections(self, project_id: Optional[str] = None) -> List[Inspection]:
        query = self.db.query(Inspection)
        if project_id:
            query = query.filter(Inspection.project_id == project_id)
        return query.order_by(Inspection.scheduled_date.desc()).all()
    
    def get_inspection(self, inspection_id: str) -> Optional[Inspection]:
        return self.db.query(Inspection).filter(Inspection.id == inspection_id).first()
    
    def create_inspection(self, inspection_data: dict) -> Inspection:
        inspection = Inspection(id=str(uuid.uuid4()), **inspection_data)
        self.db.add(inspection)
        self.db.commit()
        self.db.refresh(inspection)
        return inspection
    
    def update_inspection(self, inspection_id: str, updates: dict) -> Optional[Inspection]:
        inspection = self.get_inspection(inspection_id)
        if not inspection:
            return None
        for key, value in updates.items():
            setattr(inspection, key, value)
        self.db.commit()
        self.db.refresh(inspection)
        return inspection
    
    # Drawing Objects
    def get_objects(self, project_id: Optional[str] = None) -> List[DrawingObject]:
        query = self.db.query(DrawingObject)
        if project_id:
            query = query.filter(DrawingObject.project_id == project_id)
        return query.all()
    
    def get_object(self, object_id: str) -> Optional[DrawingObject]:
        return self.db.query(DrawingObject).filter(DrawingObject.id == object_id).first()
    
    # AI Insights
    def get_insights(self, project_id: Optional[str] = None, limit: Optional[int] = None) -> List[AIInsight]:
        query = self.db.query(AIInsight)
        if project_id:
            query = query.filter(AIInsight.project_id == project_id)
        query = query.order_by(AIInsight.created_at.desc())
        if limit:
            query = query.limit(limit)
        return query.all()
    
    def resolve_insight(self, insight_id: str) -> Optional[AIInsight]:
        insight = self.db.query(AIInsight).filter(AIInsight.id == insight_id).first()
        if not insight:
            return None
        insight.resolved = True
        self.db.commit()
        self.db.refresh(insight)
        return insight
    
    # Dashboard Stats
    def get_dashboard_stats(self) -> DashboardStats:
        projects = self.get_projects()
        submittals = self.get_submittals()
        rfis = self.get_rfis()
        inspections = self.get_inspections()
        insights = self.get_insights()
        
        today = date.today()
        approved_today = len([s for s in submittals 
                             if s.status == "approved" 
                             and hasattr(s.submitted_date, 'date') 
                             and s.submitted_date.date() == today])
        
        completed_inspections = [i for i in inspections 
                                if i.status in ["passed", "failed"]]
        passed_inspections = [i for i in inspections if i.status == "passed"]
        pass_rate = int((len(passed_inspections) / len(completed_inspections) * 100) 
                       if completed_inspections else 100)
        
        critical_insights = [i for i in insights 
                           if not i.resolved and i.severity == "critical"]
        
        return DashboardStats(
            total_projects=len(projects),
            active_projects=len([p for p in projects if p.status == "active"]),
            total_submittals=len(submittals),
            pending_review=len([s for s in submittals 
                              if s.status in ["pending", "in_review"]]),
            approved_today=approved_today,
            open_rfis=len([r for r in rfis if r.status == "open"]),
            overdue_rfis=len([r for r in rfis if r.status == "overdue"]),
            scheduled_inspections=len([i for i in inspections 
                                     if i.status == "scheduled"]),
            pass_rate=pass_rate,
            ai_insights_count=len([i for i in insights if not i.resolved]),
            critical_alerts=len(critical_insights)
        )

