"""
Compatibility shim.

`backend/models/models.py` is the source of truth for ORM definitions.
This module re-exports from `models.py` so any older imports of `models.database`
keep working without duplicating model definitions.
"""

from .models import *  # noqa: F403

