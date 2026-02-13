"""
Model package exports.

We are intentionally keeping only the SQLAlchemy `Base` here until the new
data model is defined.
"""

from .database import Base

__all__ = ["Base"]

