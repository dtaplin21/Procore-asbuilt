"""
SQLAlchemy ORM model registry.

This project is keeping the SQLAlchemy *structure* (engine/session/Base) but has intentionally
cleared out the current table models and Pydantic schemas so you can redefine the data model
from scratch.

Add new ORM models here (classes inheriting from `Base`) when you’re ready.
"""

from sqlalchemy.ext.declarative import declarative_base

Base = declarative_base()

