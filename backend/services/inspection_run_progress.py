"""Coarse inspection-run progress for UI polling (page reads + pipeline phases)."""

from __future__ import annotations

import contextvars
from contextlib import contextmanager
from datetime import datetime, timezone
from typing import Any, Iterator, Literal

from sqlalchemy.orm import Session

from config import settings
from models.inspection_run import InspectionRun

ProgressMode = Literal["index", "match", "full"]
ProgressPhase = Literal[
    "following_links",
    "reading_pdf",
    "extracting_clues",
    "indexing_linked",
    "matching",
    "tracing",
    "saving_overlay",
    "done",
    "failed",
]

_COARSE_STEPS: tuple[tuple[ProgressPhase, str], ...] = (
    ("following_links", "Following linked files"),
    ("reading_pdf", "Reading evidence PDF"),
    ("extracting_clues", "Extracting clues"),
    ("indexing_linked", "Indexing linked sheets"),
    ("matching", "Matching location on master"),
    ("tracing", "Tracing utility scope"),
    ("saving_overlay", "Saving overlay"),
)

_INDEX_PHASES = frozenset(
    {"following_links", "reading_pdf", "extracting_clues", "indexing_linked", "done", "failed"}
)
_MATCH_PHASES = frozenset({"matching", "tracing", "saving_overlay", "done", "failed"})

_progress_ctx: contextvars.ContextVar["InspectionProgressHandle | None"] = contextvars.ContextVar(
    "inspection_progress_handle",
    default=None,
)


def get_inspection_progress() -> "InspectionProgressHandle | None":
    return _progress_ctx.get()


def _ocr_backend_label() -> str:
    if settings.document_ai_enabled:
        return "document_ai"
    backend = str(settings.ocr_backend or "auto")
    return backend


def _models_snapshot() -> dict[str, str | None]:
    return {
        "ocr_backend": _ocr_backend_label(),
        "vision_model": str(settings.openai_vision_model or "").strip() or None,
    }


def _step_statuses(
    active_phase: ProgressPhase,
    *,
    mode: ProgressMode,
) -> list[dict[str, Any]]:
    phase_order = [p for p, _ in _COARSE_STEPS]
    if mode == "index":
        allowed = _INDEX_PHASES
    elif mode == "match":
        allowed = _MATCH_PHASES
    else:
        allowed = frozenset(phase_order) | {"done", "failed"}

    active_index = (
        phase_order.index(active_phase) if active_phase in phase_order else len(phase_order)
    )
    steps: list[dict[str, Any]] = []
    for phase, label in _COARSE_STEPS:
        if phase not in allowed:
            continue
        phase_index = phase_order.index(phase)
        if active_phase == "done":
            status = "done"
        elif active_phase == "failed":
            if phase_index < active_index:
                status = "done"
            elif phase_index == active_index:
                status = "error"
            else:
                status = "pending"
        elif phase_index < active_index:
            status = "done"
        elif phase_index == active_index:
            status = "running"
        else:
            status = "pending"
        steps.append({"id": phase, "label": label, "status": status})
    return steps


def _default_payload(
    *,
    run_id: int,
    job_id: int | None,
    mode: ProgressMode,
    phase: ProgressPhase,
    current_label: str,
    detail: str | None = None,
    page: int | None = None,
    page_total: int | None = None,
    file_name: str | None = None,
    error: str | None = None,
) -> dict[str, Any]:
    return {
        "run_id": run_id,
        "job_id": job_id,
        "mode": mode,
        "phase": phase,
        "updated_at": datetime.now(timezone.utc).isoformat(),
        "models": _models_snapshot(),
        "current": {
            "label": current_label,
            "detail": detail,
            "page": page,
            "page_total": page_total,
            "file_name": file_name,
        },
        "steps": _step_statuses(phase, mode=mode),
        "error": error,
    }


class InspectionProgressHandle:
    def __init__(
        self,
        session: Session,
        *,
        run_id: int,
        job_id: int | None,
        mode: ProgressMode,
    ) -> None:
        self._session = session
        self.run_id = run_id
        self.job_id = job_id
        self.mode = mode
        self._file_name: str | None = None
        self._last_phase: ProgressPhase = "matching" if mode == "match" else "following_links"

    def set_file_name(self, file_name: str | None) -> None:
        self._file_name = file_name.strip() if file_name and file_name.strip() else None

    def _write(self, payload: dict[str, Any]) -> None:
        run = self._session.get(InspectionRun, self.run_id)
        if run is None:
            return
        run.progress_json = payload  # type: ignore[assignment]
        self._session.commit()

    def start(self) -> None:
        first_phase: ProgressPhase = (
            "matching" if self.mode == "match" else "following_links"
        )
        label = next(l for p, l in _COARSE_STEPS if p == first_phase)
        self._write(
            _default_payload(
                run_id=self.run_id,
                job_id=self.job_id,
                mode=self.mode,
                phase=first_phase,
                current_label=label,
            )
        )

    def set_phase(self, phase: ProgressPhase, *, detail: str | None = None) -> None:
        self._last_phase = phase
        label = next((l for p, l in _COARSE_STEPS if p == phase), phase.replace("_", " ").title())
        self._write(
            _default_payload(
                run_id=self.run_id,
                job_id=self.job_id,
                mode=self.mode,
                phase=phase,
                current_label=label,
                detail=detail,
                file_name=self._file_name,
            )
        )

    def set_reading_page(self, page: int, page_total: int) -> None:
        self._last_phase = "reading_pdf"
        file_bit = f" — {self._file_name}" if self._file_name else ""
        self._write(
            _default_payload(
                run_id=self.run_id,
                job_id=self.job_id,
                mode=self.mode,
                phase="reading_pdf",
                current_label=f"Reading page {page} of {page_total}{file_bit}",
                page=page,
                page_total=page_total,
                file_name=self._file_name,
            )
        )

    def finish(self) -> None:
        self._write(
            _default_payload(
                run_id=self.run_id,
                job_id=self.job_id,
                mode=self.mode,
                phase="done",
                current_label="Complete",
            )
        )

    def fail(self, message: str) -> None:
        failed_at = self._last_phase
        label = next((l for p, l in _COARSE_STEPS if p == failed_at), "Failed")
        payload = _default_payload(
            run_id=self.run_id,
            job_id=self.job_id,
            mode=self.mode,
            phase="failed",
            current_label=f"Failed during: {label}",
            error=message[:500],
        )
        phase_order = [p for p, _ in _COARSE_STEPS]
        failed_index = phase_order.index(failed_at) if failed_at in phase_order else 0
        steps: list[dict[str, Any]] = []
        for phase, step_label in _COARSE_STEPS:
            if self.mode == "index" and phase not in _INDEX_PHASES:
                continue
            if self.mode == "match" and phase not in _MATCH_PHASES:
                continue
            idx = phase_order.index(phase)
            if idx < failed_index:
                status = "done"
            elif idx == failed_index:
                status = "error"
            else:
                status = "pending"
            steps.append({"id": phase, "label": step_label, "status": status})
        payload["steps"] = steps
        self._write(payload)


@contextmanager
def inspection_progress_scope(
    session: Session,
    *,
    run_id: int | None,
    job_id: int | None,
    index_only: bool,
    match_only: bool,
) -> Iterator[InspectionProgressHandle | None]:
    if run_id is None:
        yield None
        return

    if match_only:
        mode: ProgressMode = "match"
    elif index_only:
        mode = "index"
    else:
        mode = "full"

    handle = InspectionProgressHandle(session, run_id=run_id, job_id=job_id, mode=mode)
    token = _progress_ctx.set(handle)
    try:
        handle.start()
        yield handle
    finally:
        _progress_ctx.reset(token)


def finish_run_progress(run_id: int) -> None:
    from database import SessionLocal

    db = SessionLocal()
    try:
        run = db.get(InspectionRun, run_id)
        if run is None:
            return
        existing = run.progress_json if isinstance(run.progress_json, dict) else {}
        mode_raw = existing.get("mode", "full")
        mode: ProgressMode = (
            mode_raw if mode_raw in {"index", "match", "full"} else "full"
        )
        handle = InspectionProgressHandle(
            db,
            run_id=run_id,
            job_id=existing.get("job_id") if isinstance(existing.get("job_id"), int) else None,
            mode=mode,
        )
        handle.finish()
    finally:
        db.close()


def fail_run_progress(run_id: int, message: str) -> None:
    from database import SessionLocal

    db = SessionLocal()
    try:
        run = db.get(InspectionRun, run_id)
        if run is None:
            return
        existing = run.progress_json if isinstance(run.progress_json, dict) else {}
        mode_raw = existing.get("mode", "full")
        mode: ProgressMode = (
            mode_raw if mode_raw in {"index", "match", "full"} else "full"
        )
        handle = InspectionProgressHandle(
            db,
            run_id=run_id,
            job_id=existing.get("job_id") if isinstance(existing.get("job_id"), int) else None,
            mode=mode,
        )
        last = existing.get("phase")
        if last in {
            "following_links",
            "reading_pdf",
            "extracting_clues",
            "indexing_linked",
            "matching",
            "tracing",
            "saving_overlay",
        }:
            handle._last_phase = last  # noqa: SLF001
        handle.fail(message)
    finally:
        db.close()


def get_run_progress(session: Session, *, project_id: int, run_id: int) -> dict[str, Any] | None:
    run = (
        session.query(InspectionRun)
        .filter(InspectionRun.id == run_id, InspectionRun.project_id == project_id)
        .first()
    )
    if run is None:
        return None
    raw = getattr(run, "progress_json", None)
    return dict(raw) if isinstance(raw, dict) else None
