# models/database.py
from sqlalchemy import Column, Integer, String, DateTime, Boolean, ForeignKey, Text, Float, JSON
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import relationship
from datetime import datetime, timezone

Base = declarative_base()

# OAuth & User Management
class User(Base):
    __tablename__ = "users"
    
    id = Column(Integer, primary_key=True, index=True)
    email = Column(String, unique=True, index=True, nullable=False)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    
    # Relationships
    companies = relationship("UserCompany", back_populates="user")
    settings = relationship("UserSettings", back_populates="user", uselist=False)
    usage_logs = relationship("UsageLog", back_populates="user")

class Company(Base):
    __tablename__ = "companies"
    
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, nullable=False)
    procore_company_id = Column(String, unique=True, index=True)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    
    # Relationships
    users = relationship("UserCompany", back_populates="company")
    procore_connections = relationship("ProcoreConnection", back_populates="company")

class UserCompany(Base):
    __tablename__ = "user_companies"
    
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    company_id = Column(Integer, ForeignKey("companies.id"), nullable=False)
    role = Column(String, default="member")  # admin, member, etc.
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    
    # Relationships
    user = relationship("User", back_populates="companies")
    company = relationship("Company", back_populates="users")

class ProcoreConnection(Base):
    __tablename__ = "procore_connections"
    
    id = Column(Integer, primary_key=True, index=True)
    company_id = Column(Integer, ForeignKey("companies.id"), nullable=False)
    
    # OAuth tokens
    access_token = Column(Text, nullable=False)
    refresh_token = Column(Text, nullable=False)
    token_expires_at = Column(DateTime, nullable=False)
    
    # Procore details
    procore_user_id = Column(String)
    
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at = Column(
        DateTime,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )
    
    # Relationships
    company = relationship("Company", back_populates="procore_connections")

# Job Queue
class JobQueue(Base):
    __tablename__ = "job_queue"
    
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    company_id = Column(Integer, ForeignKey("companies.id"), nullable=False)
    
    job_type = Column(String, nullable=False)  # "drawing_markup", "clash_detection", etc.
    status = Column(String, default="pending")  # pending, processing, completed, failed
    
    # Input/Output references
    input_data = Column(JSON)  # Store drawing IDs, parameters, etc.
    output_url = Column(String)  # S3/object storage URL for result
    
    # Tracking
    started_at = Column(DateTime)
    completed_at = Column(DateTime)
    error_message = Column(Text)
    
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at = Column(
        DateTime,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )

# Usage Tracking
class UsageLog(Base):
    __tablename__ = "usage_logs"
    
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    company_id = Column(Integer, ForeignKey("companies.id"))
    
    action = Column(String, nullable=False)  # "drawing_processed", "api_call", etc.
    resource_type = Column(String)  # "drawing", "model", etc.
    
    # Metrics
    processing_time = Column(Float)  # seconds
    cost = Column(Float)  # if tracking costs
    
    metadata = Column(JSON)  # Additional data
    
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), index=True)
    
    # Relationships
    user = relationship("User", back_populates="usage_logs")

# User Settings
class UserSettings(Base):
    __tablename__ = "user_settings"
    
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), unique=True, nullable=False)
    
    # Detection settings
    detection_mode = Column(String, default="standard")  # standard, aggressive, conservative
    clash_threshold = Column(Float, default=0.5)  # detection sensitivity
    auto_markup = Column(Boolean, default=True)
    
    # Notification preferences
    email_notifications = Column(Boolean, default=True)
    slack_webhook = Column(String)
    
    # UI preferences
    preferences = Column(JSON)  # Store other custom settings
    
    updated_at = Column(
        DateTime,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )
    
    # Relationships
    user = relationship("User", back_populates="settings")

