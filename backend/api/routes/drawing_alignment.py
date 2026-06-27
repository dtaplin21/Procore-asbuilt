"""Backward-compatible re-export — region routes live in drawing_regions.py."""

from api.routes.drawing_regions import router

__all__ = ["router"]
