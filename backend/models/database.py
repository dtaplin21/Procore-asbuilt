"""
Compatibility shim.

`backend/models/models.py` is the source of truth for ORM definitions.
`backend/models/base.py` holds the shared declarative Base registry.
This module re-exports from `models.py` so any older imports of `models.database`
keep working without duplicating model definitions.
"""

from .models import *  # noqa: F403

