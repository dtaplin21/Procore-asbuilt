"""Coerce ``JobQueue.input_data`` id fields after JSON round-trip (str/bool guards)."""

from __future__ import annotations

from typing import Any


def coerce_job_int(value: Any, field_name: str) -> int:
    """Parse a queue payload id as ``int``; raises ``ValueError`` if not coercible."""
    if isinstance(value, bool):
        raise ValueError(f"job input_data {field_name!r} must not be a boolean")
    try:
        return int(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(
            f"job input_data {field_name!r} must be int-coercible, got {value!r}"
        ) from exc
