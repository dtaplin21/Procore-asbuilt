# Contract drawing markups — copy-paste plan

**Goal:** A company that uses Procore opens this app inside Procore, sees its master drawing, draws markups (polyline, revision cloud, arrow, rectangle, text note), tags each one with an inspection type and status from the controlled vocabulary, and filters the sheet by type. Every markup is saved in display-frame fractions. After every write the screen reloads what the server returned.

**How to use:** Work top to bottom. Each step is one paste or one command. Check the box, then go to the next step. Do not start the viewer mount until the backend tests and the frontend tests both pass. Do not start the Procore embed until the viewer shows a saved markup after a reload.

**Drawing this is aimed at:** project `1348`, master drawing `1722`, `Master.pdf`, one page, sheet `U2.C4.00`. The page graph, the registration solver, and the sheet audit are not part of this work.

---

## Decisions

- Markups are lines and shapes at exact points. Region-level placement is not drawn.
- A markup belongs to a drawing id and a page. A sheet number is not the key.
- Inspection type and status come from the vocabulary that is already in the repo. The API stores the canonical spelling. Anything else is a 422 with the field named.
- A point outside `[0, 1]`, a polyline with one point, or a text note with no text is rejected. The server does not clamp or repair it.
- After every write the hook reloads. A failed save does not stay on screen.
- Delete sets `deleted_at`. The row stays.

---

## Step 1 — Paths in this repo

These were checked against the tree. Use them as written in the later steps.

| What | Where |
| --- | --- |
| `SessionLocal`, `get_db` | `backend/database.py`. `Base` is defined in `backend/models/base.py` and re-exported by `database.py`. Model files under `backend/models/` import `from .base import Base`. |
| `Drawing` | `backend/models/models.py`, class `Drawing`, table `drawings`. `project_id`, `source`, and `name` are required. A test row cannot be `Drawing(id=1722)` alone. |
| App and routers | `backend/main.py`. Add the new router next to `inspection_reviews.router`. |
| Migrations | `backend/alembic/env.py`. It imports each model module. Add `import models.drawing_markup`. |
| Vocabulary | `backend/services/inspection_vocabulary.py`: `canonical_terms` and `canonicalize_vocab_term`. The same 14 types and 12 statuses are in `shared/inspection_vocabulary.ts` as `VOCABULARY`. Do not paste a second copy. |
| Frontend | React and TypeScript under `client/src/`. The Vite root is `client/`, and the config is `vite.config.ts` at the repo root. `@` is `client/src`. `@shared` is `shared/`. |
| Viewer | `client/src/components/drawings/DrawingViewer.tsx`. The page image is `data-testid="drawing-viewer-image"` inside `data-testid="drawing-viewer-stage"`. Overlays come from `useDrawingOverlays` in `client/src/hooks/use-inspection-runs.ts`. Leave them. |
| Tests | Vitest 3 and jsdom are already in the root `package.json`. `npm run test:unit` runs `src/**/*.test.ts` and `src/**/*.test.tsx` with `environment: "jsdom"` and `globals: true`. Run that from the repo root, not from `client/`. |
| Display frame | Fractions of the rendered page, `x` and `y` in `[0, 1]`, `y = 0` at the top. Rendered page for 1722: `drawings/rendered/project-1348/drawing-1722/page-1.png`. |

Procore facts, not re-checked against a live sandbox:

- Production sign-in is `https://login.procore.com` and the API is `https://api.procore.com`. Sandbox uses `https://sandbox.procore.com` for both.
- Procore's login page does not render inside an iframe. `@procore/procore-iframe-helpers` at version `0.2.3` opens a sign-in window. That GitHub repository is archived.
- Not checked: registering an embedded app, the exact `frame-ancestors` origins, and which Procore endpoints return drawing files.

```bash
grep -n "SessionLocal\|def get_db" backend/database.py
grep -n "class Drawing\b" backend/models/models.py
grep -n "def canonical_terms\|def canonicalize_vocab_term" backend/services/inspection_vocabulary.py
grep -n "include_router(inspection_reviews" backend/main.py
```

- [ ] The four greps hit the paths in the table

---

## Step 2 — Model

Paste as `backend/models/drawing_markup.py`.

```python
"""Contract-drawing markups. Coordinates are display-frame fractions in [0, 1], y = 0 at the top."""

from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import JSON, Column, DateTime, ForeignKey, Integer, String, Text

from .base import Base


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class DrawingMarkup(Base):
    __tablename__ = "drawing_markups"

    id = Column(Integer, primary_key=True)
    drawing_id = Column(Integer, ForeignKey("drawings.id", ondelete="CASCADE"), nullable=False, index=True)
    page = Column(Integer, nullable=False, default=1)
    kind = Column(String(16), nullable=False)  # polyline | cloud | arrow | rect | text
    points_json = Column(JSON, nullable=False)  # [[x, y], ...] fractions
    label = Column(Text, nullable=True)
    inspection_type = Column(String(80), nullable=True, index=True)
    status = Column(String(40), nullable=True)
    color = Column(String(9), nullable=True)  # #RRGGBB or #RRGGBBAA
    created_by = Column(String(120), nullable=False, default="unknown")
    created_at = Column(DateTime(timezone=True), nullable=False, default=_utcnow)
    updated_at = Column(DateTime(timezone=True), nullable=False, default=_utcnow, onupdate=_utcnow)
    deleted_at = Column(DateTime(timezone=True), nullable=True)
```

- [x] File saved

---

## Step 3 — Service

Paste as `backend/services/drawing_markups.py`. Types and statuses come from `inspection_vocabulary.py`, including aliases such as `Rough-In` and `AAN`.

```python
"""Validation and persistence for contract-drawing markups."""

from __future__ import annotations

import re
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import func
from sqlalchemy.orm import Session

from models.drawing_markup import DrawingMarkup
from services.inspection_vocabulary import (
    VocabCategory,
    canonicalize_vocab_term,
    canonical_terms,
)

INSPECTION_STATUSES = canonical_terms(VocabCategory.INSPECTION_STATUS)
INSPECTION_TYPES = canonical_terms(VocabCategory.INSPECTION_TYPE)

KINDS = ("polyline", "cloud", "arrow", "rect", "text")
MAX_POINTS = 5000
COLOR_RE = re.compile(r"^#[0-9a-fA-F]{6}([0-9a-fA-F]{2})?$")
_MIN_POINTS = {"polyline": 2, "cloud": 3}
_EXACT_POINTS = {"arrow": 2, "rect": 2, "text": 1}
_FIELD_CATEGORY = {
    "inspection_type": VocabCategory.INSPECTION_TYPE,
    "status": VocabCategory.INSPECTION_STATUS,
}


class MarkupError(ValueError):
    """Raised for input that must be rejected. The route turns it into a 422."""


def _canon(value: str | None, field: str) -> str | None:
    if value is None or not str(value).strip():
        return None
    hit = canonicalize_vocab_term(str(value), _FIELD_CATEGORY[field])
    if hit is None:
        raise MarkupError(f"{field} {value!r} is not in the controlled vocabulary")
    return hit


def clean_points(kind: str, points: Any) -> list[list[float]]:
    if kind not in KINDS:
        raise MarkupError(f"kind must be one of {', '.join(KINDS)}")
    if not isinstance(points, (list, tuple)):
        raise MarkupError("points must be a list of [x, y]")
    if len(points) > MAX_POINTS:
        raise MarkupError(f"at most {MAX_POINTS} points")
    out: list[list[float]] = []
    for pt in points:
        if not isinstance(pt, (list, tuple)) or len(pt) != 2:
            raise MarkupError("each point must be [x, y]")
        try:
            x, y = float(pt[0]), float(pt[1])
        except (TypeError, ValueError) as exc:
            raise MarkupError("point coordinates must be numbers") from exc
        if not (0.0 <= x <= 1.0 and 0.0 <= y <= 1.0):
            raise MarkupError("points are display fractions and must lie in [0, 1]; check the frame")
        out.append([x, y])
    if kind in _EXACT_POINTS and len(out) != _EXACT_POINTS[kind]:
        raise MarkupError(f"{kind} needs exactly {_EXACT_POINTS[kind]} point(s)")
    if kind in _MIN_POINTS and len(out) < _MIN_POINTS[kind]:
        raise MarkupError(f"{kind} needs at least {_MIN_POINTS[kind]} points")
    return out


def validate(
    *, kind: str, points: Any, label: str | None, inspection_type: str | None, status: str | None, color: str | None
) -> dict[str, Any]:
    pts = clean_points(kind, points)
    text = (label or "").strip() or None
    if kind == "text" and not text:
        raise MarkupError("a text markup needs a label")
    if color is not None and not COLOR_RE.match(color):
        raise MarkupError("color must be #RRGGBB or #RRGGBBAA")
    return {
        "kind": kind,
        "points_json": pts,
        "label": text,
        "inspection_type": _canon(inspection_type, "inspection_type"),
        "status": _canon(status, "status"),
        "color": color,
    }


def create_markup(
    db: Session, *, drawing_id: int, page: int, created_by: str, kind: str, points: Any,
    label: str | None = None, inspection_type: str | None = None, status: str | None = None, color: str | None = None,
) -> DrawingMarkup:
    if page < 1:
        raise MarkupError("page starts at 1")
    fields = validate(kind=kind, points=points, label=label, inspection_type=inspection_type, status=status, color=color)
    row = DrawingMarkup(drawing_id=drawing_id, page=page, created_by=(created_by or "unknown")[:120], **fields)
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


def get_markup(db: Session, markup_id: int) -> DrawingMarkup | None:
    row = db.get(DrawingMarkup, markup_id)
    return None if row is None or row.deleted_at is not None else row


def list_markups(
    db: Session, drawing_id: int, *, page: int | None = None, inspection_type: str | None = None, status: str | None = None
) -> list[DrawingMarkup]:
    query = db.query(DrawingMarkup).filter(DrawingMarkup.drawing_id == drawing_id, DrawingMarkup.deleted_at.is_(None))
    if page is not None:
        query = query.filter(DrawingMarkup.page == page)
    if inspection_type:
        query = query.filter(DrawingMarkup.inspection_type == _canon(inspection_type, "inspection_type"))
    if status:
        query = query.filter(DrawingMarkup.status == _canon(status, "status"))
    return query.order_by(DrawingMarkup.id).all()


def update_markup(db: Session, row: DrawingMarkup, changes: dict[str, Any]) -> DrawingMarkup:
    allowed = {"points", "label", "inspection_type", "status", "color"}
    unknown = set(changes) - allowed
    if unknown:
        raise MarkupError(f"cannot change {', '.join(sorted(unknown))}")
    merged = {
        "kind": row.kind,
        "points": changes.get("points", row.points_json),
        "label": changes.get("label", row.label),
        "inspection_type": changes.get("inspection_type", row.inspection_type),
        "status": changes.get("status", row.status),
        "color": changes.get("color", row.color),
    }
    fields = validate(**merged)
    for key, value in fields.items():
        setattr(row, key, value)
    db.commit()
    db.refresh(row)
    return row


def delete_markup(db: Session, row: DrawingMarkup) -> None:
    row.deleted_at = datetime.now(timezone.utc)
    db.commit()


def summary(db: Session, drawing_id: int, page: int | None = None) -> list[dict[str, Any]]:
    query = db.query(DrawingMarkup.inspection_type, DrawingMarkup.status, func.count(DrawingMarkup.id)).filter(
        DrawingMarkup.drawing_id == drawing_id, DrawingMarkup.deleted_at.is_(None)
    )
    if page is not None:
        query = query.filter(DrawingMarkup.page == page)
    rows = query.group_by(DrawingMarkup.inspection_type, DrawingMarkup.status).all()
    return sorted(
        ({"inspection_type": t, "status": s, "count": int(c)} for t, s, c in rows),
        key=lambda r: (r["inspection_type"] or "", r["status"] or ""),
    )
```

- [x] File saved

---

## Step 4 — Routes

Paste as `backend/api/routes/drawing_markups.py`.

`current_user_name` reads `X-Procore-User`. That header is a label. Swap the dependency for the app's real auth before a real user can call this. The route keeps its own `get_db` so the test can replace `routes.SessionLocal` without touching `database.py`.

```python
"""Routes for contract-drawing markups. Mount with ``app.include_router(drawing_markups.router)``."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from fastapi import APIRouter, Depends, Header, HTTPException, Query
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.orm import Session

from database import SessionLocal
from models.models import Drawing
from services import drawing_markups as svc

router = APIRouter(tags=["drawing-markups"])


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def current_user_name(x_procore_user: str | None = Header(default=None)) -> str:
    """Replace with the app's real auth dependency. This reads the name the embed bridge sends."""
    return (x_procore_user or "unknown").strip() or "unknown"


class MarkupIn(BaseModel):
    page: int = Field(default=1, ge=1)
    kind: str
    points: list[list[float]]
    label: str | None = None
    inspection_type: str | None = None
    status: str | None = None
    color: str | None = None


class MarkupPatch(BaseModel):
    model_config = ConfigDict(extra="forbid")
    points: list[list[float]] | None = None
    label: str | None = None
    inspection_type: str | None = None
    status: str | None = None
    color: str | None = None


class MarkupOut(BaseModel):
    model_config = ConfigDict(from_attributes=True, populate_by_name=True)
    id: int
    drawingId: int = Field(validation_alias="drawing_id")
    page: int
    kind: str
    points: list[list[float]] = Field(validation_alias="points_json")
    label: str | None
    inspectionType: str | None = Field(validation_alias="inspection_type")
    status: str | None
    color: str | None
    createdBy: str = Field(validation_alias="created_by")
    createdAt: datetime = Field(validation_alias="created_at")
    updatedAt: datetime = Field(validation_alias="updated_at")


def _drawing_or_404(db: Session, drawing_id: int) -> None:
    if db.get(Drawing, drawing_id) is None:
        raise HTTPException(404, f"drawing {drawing_id} not found")


@router.get("/api/drawings/{drawing_id}/markups", response_model=list[MarkupOut])
def list_markups(
    drawing_id: int,
    page: int | None = Query(default=None, ge=1),
    inspection_type: str | None = None,
    status: str | None = None,
    db: Session = Depends(get_db),
):
    _drawing_or_404(db, drawing_id)
    try:
        return svc.list_markups(db, drawing_id, page=page, inspection_type=inspection_type, status=status)
    except svc.MarkupError as exc:
        raise HTTPException(422, str(exc)) from exc


@router.post("/api/drawings/{drawing_id}/markups", response_model=MarkupOut, status_code=201)
def create_markup(drawing_id: int, body: MarkupIn, db: Session = Depends(get_db), user: str = Depends(current_user_name)):
    _drawing_or_404(db, drawing_id)
    try:
        return svc.create_markup(
            db, drawing_id=drawing_id, page=body.page, created_by=user, kind=body.kind, points=body.points,
            label=body.label, inspection_type=body.inspection_type, status=body.status, color=body.color,
        )
    except svc.MarkupError as exc:
        raise HTTPException(422, str(exc)) from exc


@router.patch("/api/markups/{markup_id}", response_model=MarkupOut)
def patch_markup(markup_id: int, body: MarkupPatch, db: Session = Depends(get_db)):
    row = svc.get_markup(db, markup_id)
    if row is None:
        raise HTTPException(404, "markup not found")
    try:
        return svc.update_markup(db, row, body.model_dump(exclude_unset=True))
    except svc.MarkupError as exc:
        raise HTTPException(422, str(exc)) from exc


@router.delete("/api/markups/{markup_id}", status_code=204)
def remove_markup(markup_id: int, db: Session = Depends(get_db)):
    row = svc.get_markup(db, markup_id)
    if row is None:
        raise HTTPException(404, "markup not found")
    svc.delete_markup(db, row)


@router.get("/api/drawings/{drawing_id}/markups/summary")
def markup_summary(drawing_id: int, page: int | None = Query(default=None, ge=1), db: Session = Depends(get_db)) -> list[dict[str, Any]]:
    _drawing_or_404(db, drawing_id)
    return svc.summary(db, drawing_id, page)
```

- [x] File saved

---

## Step 5 — Register the model and the router

In `backend/database.py`, next to the other model imports:

```python
import models.drawing_markup  # noqa: F401
```

In `backend/alembic/env.py`, next to the other model imports:

```python
import models.drawing_markup  # noqa: F401
```

In `backend/main.py`, add `drawing_markups` to the `from api.routes import (` list, then next to the other `include_router` lines:

```python
app.include_router(drawing_markups.router)
```

- [x] Three edits saved

---

## Step 6 — Migration

From `backend/`:

```bash
./venv/bin/alembic revision --autogenerate -m "add drawing_markups"
```

Open the new file in `backend/alembic/versions`. It should create `drawing_markups` and indexes on `drawing_id` and `inspection_type`. Then:

```bash
./venv/bin/alembic upgrade head
```

- [x] Migration file read
- [x] `alembic upgrade head` applied

---

## Step 7 — Backend test

Paste as `backend/tests/test_drawing_markups.py`.

The fixture builds SQLite and creates only `companies`, `projects`, `drawings`, and `drawing_markups`. `Drawing` in this repo requires `project_id`, `source`, and `name`. Creating every table on `Base` pulls Postgres-only columns from other models.

```python
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

import database
from api.routes import drawing_markups as routes
from models.drawing_markup import DrawingMarkup
from models.models import Company, Drawing, Project
from services import drawing_markups as svc


@pytest.fixture()
def client(monkeypatch):
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Session = sessionmaker(bind=engine)
    database.Base.metadata.create_all(
        engine,
        tables=[
            Company.__table__,
            Project.__table__,
            Drawing.__table__,
            DrawingMarkup.__table__,
        ],
    )
    monkeypatch.setattr(routes, "SessionLocal", Session)
    s = Session()
    s.add(Company(id=1, name="Co", procore_company_id="co-markups"))
    s.add(Project(id=1, company_id=1, procore_project_id="1348", name="Markups"))
    s.add(Drawing(id=1722, project_id=1, source="upload", name="Master.pdf"))
    s.commit()
    s.close()
    app = FastAPI()
    app.include_router(routes.router)
    return TestClient(app)


BODY = {"kind": "polyline", "points": [[0.26, 0.79], [0.35, 0.81]], "inspection_type": "underground piping", "status": "open"}


def test_create_list_roundtrip_and_vocabulary_is_canonical(client):
    r = client.post("/api/drawings/1722/markups", json=BODY, headers={"X-Procore-User": "Dom"})
    assert r.status_code == 201, r.text
    out = r.json()
    assert out["inspectionType"] == "Underground Piping" and out["status"] == "Open" and out["createdBy"] == "Dom"
    rows = client.get("/api/drawings/1722/markups", params={"inspection_type": "Underground Piping"}).json()
    assert [x["id"] for x in rows] == [out["id"]]
    assert client.get("/api/drawings/1722/markups", params={"inspection_type": "Final"}).json() == []


@pytest.mark.parametrize(
    "patch",
    [
        {"kind": "polyline", "points": [[0.1, 0.1]]},
        {"kind": "polyline", "points": [[0.1, 0.1], [0.2, 1.4]]},
        {"kind": "arrow", "points": [[0.1, 0.1], [0.2, 0.2], [0.3, 0.3]]},
        {"kind": "text", "points": [[0.1, 0.1]]},
        {"kind": "blob", "points": [[0.1, 0.1], [0.2, 0.2]]},
        {"kind": "rect", "points": [[0.1, 0.1], [0.2, 0.2]], "status": "Maybe"},
        {"kind": "rect", "points": [[0.1, 0.1], [0.2, 0.2]], "color": "red"},
    ],
)
def test_bad_input_is_rejected(client, patch):
    assert client.post("/api/drawings/1722/markups", json=patch).status_code == 422


def test_unknown_drawing_and_unknown_markup(client):
    assert client.post("/api/drawings/9/markups", json=BODY).status_code == 404
    assert client.patch("/api/markups/99", json={"label": "x"}).status_code == 404
    assert client.delete("/api/markups/99").status_code == 404


def test_patch_validates_against_the_stored_kind_and_rejects_extras(client):
    mid = client.post("/api/drawings/1722/markups", json=BODY).json()["id"]
    ok = client.patch(f"/api/markups/{mid}", json={"status": "Closed", "points": [[0.3, 0.3], [0.4, 0.4], [0.5, 0.5]]})
    assert ok.status_code == 200 and ok.json()["status"] == "Closed" and len(ok.json()["points"]) == 3
    assert client.patch(f"/api/markups/{mid}", json={"points": [[0.3, 0.3]]}).status_code == 422
    assert client.patch(f"/api/markups/{mid}", json={"kind": "cloud"}).status_code == 422


def test_delete_is_soft_and_summary_counts_live_rows(client):
    a = client.post("/api/drawings/1722/markups", json=BODY).json()["id"]
    client.post("/api/drawings/1722/markups", json={**BODY, "status": "Closed"})
    client.post("/api/drawings/1722/markups", json={**BODY, "page": 2})
    assert client.delete(f"/api/markups/{a}").status_code == 204
    assert client.get("/api/drawings/1722/markups").json().__len__() == 2
    assert client.delete(f"/api/markups/{a}").status_code == 404
    s = client.get("/api/drawings/1722/markups/summary", params={"page": 1}).json()
    assert s == [{"inspection_type": "Underground Piping", "status": "Closed", "count": 1}]


def test_service_rejects_non_numbers_and_nan():
    with pytest.raises(svc.MarkupError):
        svc.clean_points("polyline", [[0, 0], ["a", 1]])
    with pytest.raises(svc.MarkupError):
        svc.clean_points("polyline", [[0, 0], [float("nan"), 0.5]])
```

- [x] File saved

---

## Step 8 — Run the backend tests

Stop here until this passes. Later steps assume the API shape.

```bash
cd backend
PYTHONPATH=. ./venv/bin/python -m pytest -q tests/test_drawing_markups.py
```

Expected: `12 passed`.

- [x] `12 passed`

---

## Step 9 — Markup types

Paste as `client/src/types/drawing_markup.ts`.

```ts
export type MarkupKind = "polyline" | "cloud" | "arrow" | "rect" | "text";
export type MarkupTool = MarkupKind | "select";

/** A point in display-frame fractions: x and y in [0, 1], y = 0 at the top of the rendered page. */
export type Pt = [number, number];

export interface DrawingMarkup {
  id: number;
  drawingId: number;
  page: number;
  kind: MarkupKind;
  points: Pt[];
  label: string | null;
  inspectionType: string | null;
  status: string | null;
  color: string | null;
  createdBy: string;
  createdAt: string;
  updatedAt: string;
}

export interface NewMarkup {
  page: number;
  kind: MarkupKind;
  points: Pt[];
  label?: string | null;
  inspectionType?: string | null;
  status?: string | null;
  color?: string | null;
}

export interface MarkupSummaryRow {
  inspection_type: string | null;
  status: string | null;
  count: number;
}
```

- [x] File saved

---

## Step 10 — Geometry

Paste as `client/src/lib/markup_geometry.ts`.

```ts
import type { DrawingMarkup, Pt } from "../types/drawing_markup";

export const clamp01 = (v: number): number => (Number.isFinite(v) ? Math.min(1, Math.max(0, v)) : 0);

/** Pointer position to a display fraction of the element, clamped to the page. */
export function toFraction(rect: { left: number; top: number; width: number; height: number }, clientX: number, clientY: number): Pt {
  if (rect.width <= 0 || rect.height <= 0) return [0, 0];
  return [clamp01((clientX - rect.left) / rect.width), clamp01((clientY - rect.top) / rect.height)];
}

/** Distance from p to segment ab, in the same units as the inputs. */
export function distToSegment(p: Pt, a: Pt, b: Pt): number {
  const vx = b[0] - a[0];
  const vy = b[1] - a[1];
  const l2 = vx * vx + vy * vy;
  const t = l2 === 0 ? 0 : Math.max(0, Math.min(1, ((p[0] - a[0]) * vx + (p[1] - a[1]) * vy) / l2));
  return Math.hypot(p[0] - (a[0] + t * vx), p[1] - (a[1] + t * vy));
}

/** The outline of a markup as a list of vertices. Rectangles and clouds are closed. */
export function outline(m: Pick<DrawingMarkup, "kind" | "points">): Pt[] {
  const p = m.points;
  if (m.kind === "rect" && p.length === 2) {
    const [a, b] = p;
    return [[a[0], a[1]], [b[0], a[1]], [b[0], b[1]], [a[0], b[1]], [a[0], a[1]]];
  }
  if (m.kind === "cloud" && p.length >= 3) return [...p, p[0]];
  return p;
}

function inPolygon(pt: Pt, poly: Pt[]): boolean {
  let inside = false;
  for (let i = 0, j = poly.length - 1; i < poly.length; j = i++) {
    const [xi, yi] = poly[i];
    const [xj, yj] = poly[j];
    if (yi > pt[1] !== yj > pt[1] && pt[0] < ((xj - xi) * (pt[1] - yi)) / (yj - yi) + xi) inside = !inside;
  }
  return inside;
}

/** Distance from a point to a markup. Text is a point. Closed shapes count as 0 inside. */
export function distanceToMarkup(m: DrawingMarkup, pt: Pt): number {
  if (m.kind === "text") return Math.hypot(pt[0] - m.points[0][0], pt[1] - m.points[0][1]);
  const poly = outline(m);
  if ((m.kind === "rect" || m.kind === "cloud") && inPolygon(pt, poly)) return 0;
  let best = Infinity;
  for (let i = 0; i + 1 < poly.length; i++) best = Math.min(best, distToSegment(pt, poly[i], poly[i + 1]));
  return best;
}

/** The nearest markup within tol (a page fraction), later markups winning ties so the top one is picked. */
export function hitTest(markups: DrawingMarkup[], pt: Pt, tol = 0.01): DrawingMarkup | null {
  let best: DrawingMarkup | null = null;
  let bestD = tol;
  for (const m of markups) {
    const d = distanceToMarkup(m, pt);
    if (d <= bestD) {
      best = m;
      bestD = d;
    }
  }
  return best;
}

/** Scalloped outline for a revision cloud: one outward arc per `bump` of edge length. */
export function cloudPath(points: Pt[], bump = 0.015): string {
  if (points.length < 3) return "";
  const ring: Pt[] = [...points, points[0]];
  let d = `M ${ring[0][0]} ${ring[0][1]}`;
  for (let i = 0; i + 1 < ring.length; i++) {
    const [x0, y0] = ring[i];
    const [x1, y1] = ring[i + 1];
    const len = Math.hypot(x1 - x0, y1 - y0);
    const n = Math.max(1, Math.round(len / bump));
    const r = len / n / 2;
    for (let k = 1; k <= n; k++) {
      const x = x0 + ((x1 - x0) * k) / n;
      const y = y0 + ((y1 - y0) * k) / n;
      d += ` A ${r} ${r} 0 0 1 ${x} ${y}`;
    }
  }
  return `${d} Z`;
}

const PALETTE = ["#d1495b", "#00798c", "#edae49", "#66a182", "#30638e", "#8d6a9f", "#c97b3d", "#4c6b8a"];

/** A stable colour for an inspection type, so the same type is the same colour on every sheet. */
export function typeColor(inspectionType: string | null | undefined): string {
  if (!inspectionType) return "#555555";
  let h = 0;
  for (const ch of inspectionType) h = (h * 31 + ch.charCodeAt(0)) >>> 0;
  return PALETTE[h % PALETTE.length];
}

export function markupColor(m: Pick<DrawingMarkup, "color" | "inspectionType">): string {
  return m.color ?? typeColor(m.inspectionType);
}
```

- [x] File saved

---

## Step 11 — Geometry test

Paste as `client/src/lib/markup_geometry.test.ts`.

```ts
import { describe, expect, it } from "vitest";
import { cloudPath, distToSegment, hitTest, outline, toFraction, typeColor } from "./markup_geometry";
import type { DrawingMarkup } from "../types/drawing_markup";

const mk = (id: number, kind: DrawingMarkup["kind"], points: [number, number][], inspectionType: string | null = null): DrawingMarkup => ({
  id, drawingId: 1, page: 1, kind, points, label: null, inspectionType, status: null, color: null, createdBy: "t", createdAt: "", updatedAt: "",
});

describe("geometry", () => {
  it("maps pointer to fractions, y down from the top, and clamps", () => {
    const rect = { left: 100, top: 50, width: 200, height: 100 };
    expect(toFraction(rect, 200, 100)).toEqual([0.5, 0.5]);
    expect(toFraction(rect, 0, 1000)).toEqual([0, 1]);
    expect(toFraction({ ...rect, width: 0 }, 5, 5)).toEqual([0, 0]);
  });
  it("measures distance to a segment, including past the ends", () => {
    expect(distToSegment([0.5, 0.2], [0, 0], [1, 0])).toBeCloseTo(0.2);
    expect(distToSegment([2, 0], [0, 0], [1, 0])).toBeCloseTo(1);
    expect(distToSegment([0.3, 0.4], [0.1, 0.1], [0.1, 0.1])).toBeCloseTo(Math.hypot(0.2, 0.3));
  });
  it("closes rectangles and clouds", () => {
    expect(outline(mk(1, "rect", [[0.1, 0.1], [0.3, 0.2]]))).toHaveLength(5);
    const c = outline(mk(1, "cloud", [[0, 0], [1, 0], [1, 1]]));
    expect(c[c.length - 1]).toEqual(c[0]);
  });
  it("hits the nearest markup, the later one on a tie, and nothing outside tolerance", () => {
    const a = mk(1, "polyline", [[0.1, 0.5], [0.9, 0.5]]);
    const b = mk(2, "polyline", [[0.1, 0.5], [0.9, 0.5]]);
    expect(hitTest([a, b], [0.5, 0.505])?.id).toBe(2);
    expect(hitTest([a, b], [0.5, 0.7])).toBeNull();
    const box = mk(3, "rect", [[0.2, 0.2], [0.6, 0.6]]);
    expect(hitTest([box], [0.4, 0.4])?.id).toBe(3);
    expect(hitTest([mk(4, "text", [[0.5, 0.5]])], [0.505, 0.5])?.id).toBe(4);
  });
  it("draws a cloud as arcs that end back at the start", () => {
    const d = cloudPath([[0.1, 0.1], [0.4, 0.1], [0.4, 0.3]]);
    expect(d.startsWith("M 0.1 0.1")).toBe(true);
    expect((d.match(/ A /g) ?? []).length).toBeGreaterThan(10);
    expect(d.endsWith("Z")).toBe(true);
    expect(cloudPath([[0, 0], [1, 1]])).toBe("");
  });
  it("gives a type the same colour every time", () => {
    expect(typeColor("Final")).toBe(typeColor("Final"));
    expect(typeColor(null)).toBe("#555555");
  });
});
```

From the repo root:

```bash
npx vitest run src/lib/markup_geometry.test.ts
```

- [x] `6 passed` in that file

---

## Step 12 — API client

Paste as `client/src/lib/markup_api.ts`. `baseUrl` empty means same origin. The dev server already proxies `/api` to port `2000`.

```ts
import type { DrawingMarkup, MarkupSummaryRow, NewMarkup, Pt } from "../types/drawing_markup";

export interface ApiOptions {
  baseUrl?: string;
  /** Name sent as X-Procore-User. The server stores it as created_by. */
  userName?: string;
  fetchImpl?: typeof fetch;
}

export class MarkupApiError extends Error {
  constructor(public status: number, message: string) {
    super(message);
  }
}

async function call<T>(opts: ApiOptions, path: string, init: RequestInit = {}): Promise<T> {
  const f = opts.fetchImpl ?? fetch;
  const headers: Record<string, string> = { "Content-Type": "application/json" };
  if (opts.userName) headers["X-Procore-User"] = opts.userName;
  const res = await f(`${opts.baseUrl ?? ""}${path}`, { ...init, headers: { ...headers, ...(init.headers as Record<string, string>) } });
  if (res.status === 204) return undefined as T;
  const body = await res.json().catch(() => ({}));
  if (!res.ok) throw new MarkupApiError(res.status, typeof body?.detail === "string" ? body.detail : `HTTP ${res.status}`);
  return body as T;
}

export const listMarkups = (o: ApiOptions, drawingId: number, page?: number) =>
  call<DrawingMarkup[]>(o, `/api/drawings/${drawingId}/markups${page ? `?page=${page}` : ""}`);

export const markupSummary = (o: ApiOptions, drawingId: number, page?: number) =>
  call<MarkupSummaryRow[]>(o, `/api/drawings/${drawingId}/markups/summary${page ? `?page=${page}` : ""}`);

export const createMarkup = (o: ApiOptions, drawingId: number, body: NewMarkup) =>
  call<DrawingMarkup>(o, `/api/drawings/${drawingId}/markups`, {
    method: "POST",
    body: JSON.stringify({
      page: body.page, kind: body.kind, points: body.points, label: body.label ?? null,
      inspection_type: body.inspectionType ?? null, status: body.status ?? null, color: body.color ?? null,
    }),
  });

export const patchMarkup = (
  o: ApiOptions, id: number,
  changes: { points?: Pt[]; label?: string | null; inspectionType?: string | null; status?: string | null; color?: string | null },
) => {
  const body: Record<string, unknown> = {};
  if (changes.points !== undefined) body.points = changes.points;
  if (changes.label !== undefined) body.label = changes.label;
  if (changes.inspectionType !== undefined) body.inspection_type = changes.inspectionType;
  if (changes.status !== undefined) body.status = changes.status;
  if (changes.color !== undefined) body.color = changes.color;
  return call<DrawingMarkup>(o, `/api/markups/${id}`, { method: "PATCH", body: JSON.stringify(body) });
};

export const deleteMarkup = (o: ApiOptions, id: number) => call<void>(o, `/api/markups/${id}`, { method: "DELETE" });
```

- [x] File saved

---

## Step 13 — Hook

Paste as `client/src/hooks/useDrawingMarkups.ts`.

```ts
import { useCallback, useEffect, useRef, useState } from "react";
import * as api from "../lib/markup_api";
import type { DrawingMarkup, MarkupSummaryRow, NewMarkup } from "../types/drawing_markup";

export function useDrawingMarkups(drawingId: number | null, page: number, opts: api.ApiOptions = {}) {
  const [markups, setMarkups] = useState<DrawingMarkup[]>([]);
  const [summary, setSummary] = useState<MarkupSummaryRow[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const optsRef = useRef(opts);
  optsRef.current = opts;

  const reload = useCallback(async () => {
    if (drawingId == null) return;
    setLoading(true);
    try {
      const [rows, sums] = await Promise.all([
        api.listMarkups(optsRef.current, drawingId, page),
        api.markupSummary(optsRef.current, drawingId, page),
      ]);
      setMarkups(rows);
      setSummary(sums);
      setError(null);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setLoading(false);
    }
  }, [drawingId, page]);

  useEffect(() => {
    setMarkups([]);
    setSummary([]);
    void reload();
  }, [reload]);

  /** Each write reloads from the server, so the screen shows what was saved and not what was drawn. */
  const run = useCallback(async <T,>(fn: () => Promise<T>): Promise<T | null> => {
    try {
      const out = await fn();
      await reload();
      return out;
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
      return null;
    }
  }, [reload]);

  const create = useCallback((body: NewMarkup) => drawingId == null ? Promise.resolve(null) : run(() => api.createMarkup(optsRef.current, drawingId, body)), [drawingId, run]);
  const update = useCallback((id: number, changes: Parameters<typeof api.patchMarkup>[2]) => run(() => api.patchMarkup(optsRef.current, id, changes)), [run]);
  const remove = useCallback((id: number) => run(() => api.deleteMarkup(optsRef.current, id)), [run]);

  return { markups, summary, loading, error, reload, create, update, remove };
}
```

- [x] File saved

---

## Step 14 — Draw layer

Paste as `client/src/components/MarkupLayer.tsx`.

Click adds points to a polyline or cloud. Double-click or Enter finishes. Drag draws an arrow or rectangle. Click asks for a text note. Escape cancels.

```tsx
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { cloudPath, hitTest, markupColor, outline, toFraction } from "../lib/markup_geometry";
import type { DrawingMarkup, MarkupKind, MarkupTool, Pt } from "../types/drawing_markup";

export interface MarkupLayerProps {
  markups: DrawingMarkup[];
  tool: MarkupTool;
  /** Types to draw. null shows every markup. */
  visibleTypes?: ReadonlySet<string> | null;
  selectedId?: number | null;
  onSelect?: (id: number | null) => void;
  onCreate?: (kind: MarkupKind, points: Pt[], label: string | null) => void;
  /** Called for the text tool. Return null to cancel. */
  askLabel?: () => string | null;
}

const MIN_DRAG = 0.003;

/** Absolutely positioned layer. Put it inside the same box as the rendered page image, sized 100% by 100%. */
export function MarkupLayer({ markups, tool, visibleTypes = null, selectedId = null, onSelect, onCreate, askLabel }: MarkupLayerProps) {
  const ref = useRef<HTMLDivElement>(null);
  const [draft, setDraft] = useState<Pt[]>([]);
  const [hover, setHover] = useState<Pt | null>(null);
  const dragStart = useRef<Pt | null>(null);
  const multi = tool === "polyline" || tool === "cloud";

  const shown = useMemo(
    () => markups.filter((m) => visibleTypes == null || (m.inspectionType != null && visibleTypes.has(m.inspectionType)) || (m.inspectionType == null && visibleTypes.has(""))),
    [markups, visibleTypes],
  );

  const at = (e: { clientX: number; clientY: number }): Pt => toFraction(ref.current!.getBoundingClientRect(), e.clientX, e.clientY);

  const finish = useCallback(() => {
    if (multi && draft.length >= (tool === "cloud" ? 3 : 2)) onCreate?.(tool as MarkupKind, draft, null);
    setDraft([]);
    setHover(null);
  }, [draft, multi, onCreate, tool]);

  useEffect(() => {
    setDraft([]);
    setHover(null);
    dragStart.current = null;
  }, [tool]);

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") { setDraft([]); setHover(null); dragStart.current = null; }
      if (e.key === "Enter") finish();
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [finish]);

  const onPointerDown = (e: React.PointerEvent) => {
    const p = at(e);
    if (tool === "select") {
      onSelect?.(hitTest(shown, p)?.id ?? null);
    } else if (tool === "arrow" || tool === "rect") {
      dragStart.current = p;
      setHover(p);
    } else if (tool === "text") {
      const label = (askLabel ?? (() => window.prompt("Note text")))();
      if (label && label.trim()) onCreate?.("text", [p], label.trim());
    } else if (multi) {
      setDraft((d) => [...d, p]);
    }
  };
  const onPointerMove = (e: React.PointerEvent) => {
    if (tool !== "select" && tool !== "text") setHover(at(e));
  };
  const onPointerUp = (e: React.PointerEvent) => {
    const start = dragStart.current;
    dragStart.current = null;
    if (!start || (tool !== "arrow" && tool !== "rect")) return;
    const end = at(e);
    if (Math.hypot(end[0] - start[0], end[1] - start[1]) < MIN_DRAG) { setHover(null); return; }
    onCreate?.(tool, [start, end], null);
    setHover(null);
  };

  const preview: Pt[] = useMemo(() => {
    if (dragStart.current && hover && (tool === "arrow" || tool === "rect")) return [dragStart.current, hover];
    if (multi && draft.length) return hover ? [...draft, hover] : draft;
    return [];
  }, [draft, hover, multi, tool]);

  return (
    <div
      ref={ref}
      data-testid="markup-layer"
      style={{ position: "absolute", inset: 0, touchAction: "none", cursor: tool === "select" ? "default" : "crosshair" }}
      onPointerDown={onPointerDown}
      onPointerMove={onPointerMove}
      onPointerUp={onPointerUp}
      onDoubleClick={() => finish()}
    >
      <svg viewBox="0 0 1 1" preserveAspectRatio="none" width="100%" height="100%" style={{ position: "absolute", inset: 0, overflow: "visible" }}>
        <defs>
          {shown.filter((m) => m.kind === "arrow").map((m) => (
            <marker key={m.id} id={`arrowhead-${m.id}`} viewBox="0 0 10 10" refX="9" refY="5" markerWidth="8" markerHeight="8" orient="auto-start-reverse">
              <path d="M 0 0 L 10 5 L 0 10 z" fill={markupColor(m)} />
            </marker>
          ))}
        </defs>
        {shown.filter((m) => m.kind !== "text").map((m) => {
          const color = markupColor(m);
          const common = {
            stroke: color, fill: "none", strokeWidth: m.id === selectedId ? 4 : 2, vectorEffect: "non-scaling-stroke" as const,
            strokeLinejoin: "round" as const, strokeLinecap: "round" as const,
          };
          const key = `m-${m.id}`;
          if (m.kind === "cloud") return <path key={key} d={cloudPath(m.points)} {...common} fill={`${color.slice(0, 7)}22`} />;
          if (m.kind === "rect") return <polygon key={key} points={outline(m).map((p) => p.join(",")).join(" ")} {...common} fill={`${color.slice(0, 7)}22`} />;
          if (m.kind === "arrow") return <polyline key={key} points={m.points.map((p) => p.join(",")).join(" ")} {...common} markerEnd={`url(#arrowhead-${m.id})`} />;
          return <polyline key={key} points={m.points.map((p) => p.join(",")).join(" ")} {...common} />;
        })}
        {preview.length >= 2 && (
          <polyline
            data-testid="draft"
            points={(tool === "rect" ? outline({ kind: "rect", points: preview.slice(0, 2) }) : preview).map((p) => p.join(",")).join(" ")}
            stroke="#1a73e8" fill="none" strokeWidth={2} strokeDasharray="6 4" vectorEffect="non-scaling-stroke"
          />
        )}
      </svg>
      {shown.filter((m) => m.kind === "text").map((m) => (
        <div
          key={`t-${m.id}`}
          style={{
            position: "absolute", left: `${m.points[0][0] * 100}%`, top: `${m.points[0][1] * 100}%`, transform: "translate(0, -100%)",
            background: "#fffbe6", border: `2px solid ${markupColor(m)}`, padding: "2px 6px", fontSize: 12, maxWidth: 240,
            outline: m.id === selectedId ? "2px solid #1a73e8" : "none", pointerEvents: "none",
          }}
        >
          {m.label}
        </div>
      ))}
    </div>
  );
}
```

- [x] File saved

---

## Step 15 — Draw-layer test

Paste as `client/src/components/MarkupLayer.test.tsx`.

```tsx
import { act, fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { MarkupLayer } from "./MarkupLayer";
import type { DrawingMarkup } from "../types/drawing_markup";

function setup(props: Partial<React.ComponentProps<typeof MarkupLayer>> = {}) {
  const onCreate = vi.fn();
  const onSelect = vi.fn();
  render(<MarkupLayer markups={[]} tool="polyline" onCreate={onCreate} onSelect={onSelect} {...props} />);
  const layer = screen.getByTestId("markup-layer");
  layer.getBoundingClientRect = () => ({ left: 0, top: 0, width: 1000, height: 500, right: 1000, bottom: 500, x: 0, y: 0, toJSON() {} }) as DOMRect;
  return { layer, onCreate, onSelect };
}
const fire = (el: Element, type: string, x: number, y: number) =>
  act(() => { el.dispatchEvent(new MouseEvent(type, { bubbles: true, clientX: x, clientY: y })); });
const down = (el: Element, x: number, y: number) => fire(el, "pointerdown", x, y);
const up = (el: Element, x: number, y: number) => fire(el, "pointerup", x, y);

describe("MarkupLayer", () => {
  it("builds a polyline from clicks and finishes on Enter, in fractions", () => {
    const { layer, onCreate } = setup();
    down(layer, 100, 250);
    down(layer, 500, 250);
    fireEvent.keyDown(window, { key: "Enter" });
    expect(onCreate).toHaveBeenCalledWith("polyline", [[0.1, 0.5], [0.5, 0.5]], null);
  });
  it("does not create a one-point polyline", () => {
    const { layer, onCreate } = setup();
    down(layer, 10, 10);
    fireEvent.keyDown(window, { key: "Enter" });
    expect(onCreate).not.toHaveBeenCalled();
  });
  it("does not create a two-point cloud", () => {
    const { layer, onCreate } = setup({ tool: "cloud" });
    down(layer, 10, 10);
    down(layer, 200, 10);
    fireEvent.keyDown(window, { key: "Enter" });
    expect(onCreate).not.toHaveBeenCalled();
  });
  it("Escape discards the draft", () => {
    const { layer, onCreate } = setup();
    down(layer, 10, 10);
    down(layer, 300, 10);
    fireEvent.keyDown(window, { key: "Escape" });
    fireEvent.keyDown(window, { key: "Enter" });
    expect(onCreate).not.toHaveBeenCalled();
  });
  it("drags a rectangle and ignores a click without a drag", () => {
    const { layer, onCreate } = setup({ tool: "rect" });
    down(layer, 100, 100);
    up(layer, 100, 100);
    expect(onCreate).not.toHaveBeenCalled();
    down(layer, 100, 100);
    up(layer, 300, 200);
    expect(onCreate).toHaveBeenCalledWith("rect", [[0.1, 0.2], [0.3, 0.4]], null);
  });
  it("asks for text and skips an empty answer", () => {
    const ask = vi.fn().mockReturnValueOnce("  Verify slope ").mockReturnValueOnce("   ");
    const { layer, onCreate } = setup({ tool: "text", askLabel: ask });
    down(layer, 500, 250);
    down(layer, 600, 250);
    expect(onCreate).toHaveBeenCalledTimes(1);
    expect(onCreate).toHaveBeenCalledWith("text", [[0.5, 0.5]], "Verify slope");
  });
  it("selects the markup under the pointer and clears on empty space", () => {
    const line: DrawingMarkup = { id: 7, drawingId: 1, page: 1, kind: "polyline", points: [[0.1, 0.5], [0.9, 0.5]], label: null, inspectionType: "Final", status: null, color: null, createdBy: "t", createdAt: "", updatedAt: "" };
    const { layer, onSelect } = setup({ tool: "select", markups: [line] });
    down(layer, 500, 252);
    expect(onSelect).toHaveBeenLastCalledWith(7);
    down(layer, 500, 50);
    expect(onSelect).toHaveBeenLastCalledWith(null);
  });
  it("hides types that are not selected and counts untyped as the empty key", () => {
    const base = { drawingId: 1, page: 1, label: null, status: null, color: null, createdBy: "t", createdAt: "", updatedAt: "" };
    const ms: DrawingMarkup[] = [
      { ...base, id: 1, kind: "polyline", points: [[0.1, 0.1], [0.2, 0.2]], inspectionType: "Final" },
      { ...base, id: 2, kind: "polyline", points: [[0.3, 0.3], [0.4, 0.4]], inspectionType: "Flush" },
      { ...base, id: 3, kind: "polyline", points: [[0.5, 0.5], [0.6, 0.6]], inspectionType: null },
    ];
    const { container } = render(<MarkupLayer markups={ms} tool="select" visibleTypes={new Set(["Final", ""])} />);
    expect(container.querySelectorAll("polyline")).toHaveLength(2);
  });
});
```

From the repo root:

```bash
npx vitest run src/components/MarkupLayer.test.tsx
```

- [x] `8 passed` in that file

---

## Step 16 — Type filter

Paste as `client/src/components/InspectionTypeFilter.tsx`.

```tsx
import { typeColor } from "../lib/markup_geometry";
import type { MarkupSummaryRow } from "../types/drawing_markup";

export interface InspectionTypeFilterProps {
  summary: MarkupSummaryRow[];
  /** Selected types. "" stands for markups with no inspection type. */
  selected: ReadonlySet<string>;
  onChange: (next: Set<string>) => void;
}

export function InspectionTypeFilter({ summary, selected, onChange }: InspectionTypeFilterProps) {
  const byType = new Map<string, { total: number; statuses: Map<string, number> }>();
  for (const row of summary) {
    const key = row.inspection_type ?? "";
    const entry = byType.get(key) ?? { total: 0, statuses: new Map<string, number>() };
    entry.total += row.count;
    entry.statuses.set(row.status ?? "No status", (entry.statuses.get(row.status ?? "No status") ?? 0) + row.count);
    byType.set(key, entry);
  }
  const toggle = (key: string) => {
    const next = new Set(selected);
    if (next.has(key)) next.delete(key); else next.add(key);
    onChange(next);
  };
  if (byType.size === 0) return <p style={{ fontSize: 13, color: "#666" }}>No markups on this page yet.</p>;
  return (
    <ul style={{ listStyle: "none", margin: 0, padding: 0 }}>
      {[...byType.entries()].sort(([a], [b]) => a.localeCompare(b)).map(([key, entry]) => (
        <li key={key || "none"} style={{ marginBottom: 6 }}>
          <label style={{ display: "flex", gap: 8, alignItems: "center", fontSize: 13 }}>
            <input type="checkbox" checked={selected.has(key)} onChange={() => toggle(key)} />
            <span style={{ width: 12, height: 12, background: typeColor(key || null), display: "inline-block" }} />
            <span style={{ flex: 1 }}>{key || "No inspection type"}</span>
            <span>{entry.total}</span>
          </label>
          <div style={{ marginLeft: 28, fontSize: 11, color: "#666" }}>
            {[...entry.statuses.entries()].map(([s, n]) => `${s} ${n}`).join(" · ")}
          </div>
        </li>
      ))}
    </ul>
  );
}
```

- [x] File saved

---

## Step 17 — Standalone workspace

Paste as `client/src/components/MarkupWorkspace.tsx`.

The type and status lists are `VOCABULARY` from `shared/inspection_vocabulary.ts`. This page is enough to draw before the layer is mounted in `DrawingViewer`.

```tsx
import { useEffect, useMemo, useState } from "react";
import { VocabCategory, VOCABULARY } from "@shared/inspection_vocabulary";
import { useDrawingMarkups } from "../hooks/useDrawingMarkups";
import type { ApiOptions } from "../lib/markup_api";
import type { MarkupKind, MarkupTool, Pt } from "../types/drawing_markup";
import { InspectionTypeFilter } from "./InspectionTypeFilter";
import { MarkupLayer } from "./MarkupLayer";

export const INSPECTION_TYPES = VOCABULARY[VocabCategory.InspectionType];
export const INSPECTION_STATUSES = VOCABULARY[VocabCategory.InspectionStatus];
const TOOLS: MarkupTool[] = ["select", "polyline", "cloud", "arrow", "rect", "text"];

export interface MarkupWorkspaceProps {
  drawingId: number;
  page?: number;
  /** URL of the rendered page image. Its aspect ratio sets the size of the box the markups sit in. */
  pageImageUrl: string;
  /** Width over height of that image. Leave out to read it from the loaded image. */
  pageAspect?: number;
  api?: ApiOptions;
}

export function MarkupWorkspace({ drawingId, page = 1, pageImageUrl, pageAspect, api = {} }: MarkupWorkspaceProps) {
  const [naturalAspect, setNaturalAspect] = useState<number | null>(null);
  const { markups, summary, error, create, update, remove } = useDrawingMarkups(drawingId, page, api);
  const [tool, setTool] = useState<MarkupTool>("select");
  const [inspectionType, setInspectionType] = useState<string>(INSPECTION_TYPES[0]);
  const [status, setStatus] = useState<string>("Open");
  const [selectedTypes, setSelectedTypes] = useState<Set<string> | null>(null);
  const [selectedId, setSelectedId] = useState<number | null>(null);

  const allTypes = useMemo(() => new Set(summary.map((r) => r.inspection_type ?? "")), [summary]);
  const visible = selectedTypes ?? allTypes;
  useEffect(() => {
    if (selectedId != null && !markups.some((m) => m.id === selectedId)) setSelectedId(null);
  }, [markups, selectedId]);

  const selected = markups.find((m) => m.id === selectedId) ?? null;

  const onCreate = async (kind: MarkupKind, points: Pt[], label: string | null) => {
    const made = await create({ page, kind, points, label, inspectionType, status });
    if (made) setSelectedId(made.id);
  };

  return (
    <div style={{ display: "grid", gridTemplateColumns: "1fr 280px", gap: 16, alignItems: "start" }}>
      <div>
        <div role="toolbar" aria-label="Markup tools" style={{ display: "flex", gap: 6, marginBottom: 8, flexWrap: "wrap" }}>
          {TOOLS.map((t) => (
            <button key={t} aria-pressed={tool === t} onClick={() => setTool(t)} style={{ fontWeight: tool === t ? 700 : 400 }}>
              {t}
            </button>
          ))}
          <select aria-label="Inspection type" value={inspectionType} onChange={(e) => setInspectionType(e.target.value)}>
            {INSPECTION_TYPES.map((t) => <option key={t}>{t}</option>)}
          </select>
          <select aria-label="Status" value={status} onChange={(e) => setStatus(e.target.value)}>
            {INSPECTION_STATUSES.map((s) => <option key={s}>{s}</option>)}
          </select>
        </div>
        {error && <p role="alert" style={{ color: "#b00020" }}>{error}</p>}
        <div style={{ position: "relative", width: "100%", aspectRatio: String(pageAspect ?? naturalAspect ?? 1.4) }}>
          <img src={pageImageUrl} alt="Contract drawing" draggable={false}
            onLoad={(e) => { const { naturalWidth: w, naturalHeight: h } = e.currentTarget; if (w > 0 && h > 0) setNaturalAspect(w / h); }}
            style={{ position: "absolute", inset: 0, width: "100%", height: "100%" }} />
          <MarkupLayer markups={markups} tool={tool} visibleTypes={visible} selectedId={selectedId} onSelect={setSelectedId} onCreate={onCreate} />
        </div>
      </div>
      <aside>
        <h3 style={{ marginTop: 0 }}>Inspection types</h3>
        <InspectionTypeFilter summary={summary} selected={visible} onChange={setSelectedTypes} />
        {selected && (
          <section aria-label="Selected markup" style={{ marginTop: 16, fontSize: 13 }}>
            <strong>{selected.kind}</strong> #{selected.id} by {selected.createdBy}
            <div style={{ display: "flex", gap: 6, marginTop: 6 }}>
              <select aria-label="Selected status" value={selected.status ?? ""} onChange={(e) => update(selected.id, { status: e.target.value || null })}>
                <option value="">No status</option>
                {INSPECTION_STATUSES.map((s) => <option key={s}>{s}</option>)}
              </select>
              <button onClick={() => remove(selected.id)}>Delete</button>
            </div>
          </section>
        )}
      </aside>
    </div>
  );
}
```

- [ ] File saved

---

## Step 18 — Procore embed helper

From the repo root:

```bash
npm i @procore/procore-iframe-helpers@0.2.3
```

Paste as `client/src/types/procore-iframe-helpers.d.ts`. Delete it if a later package version ships types.

```ts
declare module "@procore/procore-iframe-helpers";
```

Paste as `client/src/lib/procore_embed.ts`.

```ts
/**
 * Embedded-app bridge. Procore's login page will not render inside an iframe, so sign-in opens a
 * separate window and hands the result back to the iframe. The package is archived on GitHub.
 */
interface IframeContext {
  authentication: {
    authenticate(opts: { url: string; onSuccess: (payload: unknown) => void; onFailure: (error: unknown) => void }): void;
    notifySuccess(payload?: unknown): void;
  };
}
interface HelpersModule {
  initialize(): IframeContext;
}

export function isEmbedded(win: Window = window): boolean {
  try {
    return win.self !== win.top;
  } catch {
    return true;
  }
}

let cached: IframeContext | null = null;

export async function getProcoreContext(): Promise<IframeContext | null> {
  if (!isEmbedded()) return null;
  if (cached) return cached;
  const mod = (await import("@procore/procore-iframe-helpers")) as unknown as { default?: HelpersModule } & HelpersModule;
  const helpers: HelpersModule = mod.default ?? mod;
  cached = helpers.initialize();
  return cached;
}

/** Opens the sign-in window at `url` (a route on your server that starts the OAuth redirect). */
export async function signInThroughProcore(url = "/auth/procore"): Promise<void> {
  const ctx = await getProcoreContext();
  if (!ctx) {
    window.location.assign(url);
    return;
  }
  await new Promise<void>((resolve, reject) => {
    ctx.authentication.authenticate({ url, onSuccess: () => resolve(), onFailure: (e) => reject(e instanceof Error ? e : new Error(String(e))) });
  });
}

/** Call this from the page your OAuth callback renders, so the iframe learns that sign-in finished. */
export async function notifySignInDone(): Promise<void> {
  const ctx = await getProcoreContext();
  ctx?.authentication.notifySuccess({});
}
```

Paste as `client/src/lib/procore_embed.test.ts`.

```ts
import { describe, expect, it, vi } from "vitest";
import { isEmbedded, signInThroughProcore } from "./procore_embed";

describe("procore_embed", () => {
  it("is not embedded in a top-level window", () => {
    expect(isEmbedded()).toBe(false);
  });
  it("treats a throwing cross-origin top as embedded", () => {
    const win = { self: {}, get top(): never { throw new Error("blocked"); } } as unknown as Window;
    expect(isEmbedded(win)).toBe(true);
  });
  it("signs in with a plain redirect outside Procore", async () => {
    const assign = vi.fn();
    const original = window.location;
    Object.defineProperty(window, "location", { value: { ...original, assign }, configurable: true });
    await signInThroughProcore("/auth/procore");
    expect(assign).toHaveBeenCalledWith("/auth/procore");
    Object.defineProperty(window, "location", { value: original, configurable: true });
  });
});
```

- [ ] Package installed
- [ ] Three files saved

---

## Step 19 — End-to-end test file

Paste as `client/src/components/MarkupWorkspace.e2e.test.tsx`. It stays skipped until step 23 sets `E2E_URL`.

```tsx
import { act, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { MarkupWorkspace } from "./MarkupWorkspace";

const env = (globalThis as unknown as { process?: { env: Record<string, string | undefined> } }).process?.env ?? {};
const base = env.E2E_URL;
const drawingId = Number(env.E2E_DRAWING_ID ?? 1722);
const page = Number(env.E2E_PAGE ?? 99);
const fire = (el: Element, type: string, x: number, y: number) =>
  act(() => { el.dispatchEvent(new MouseEvent(type, { bubbles: true, clientX: x, clientY: y })); });

describe.skipIf(!base)("MarkupWorkspace against the real API", () => {
  it("draws, saves, filters by inspection type, changes status, deletes", async () => {
    render(<MarkupWorkspace drawingId={drawingId} page={page} pageImageUrl="data:image/gif;base64,R0lGODlhAQABAAAAACw=" pageAspect={1.4} api={{ baseUrl: base, userName: "Dom" }} />);
    await screen.findByText("No markups on this page yet.");

    const layer = screen.getByTestId("markup-layer");
    layer.getBoundingClientRect = () => ({ left: 0, top: 0, width: 1000, height: 500, right: 1000, bottom: 500, x: 0, y: 0, toJSON() {} }) as DOMRect;
    fireEvent.click(screen.getByRole("button", { name: "polyline" }));
    fireEvent.change(screen.getByLabelText("Inspection type"), { target: { value: "Underground Piping" } });
    fire(layer, "pointerdown", 260, 395);
    fire(layer, "pointerdown", 350, 405);
    fireEvent.keyDown(window, { key: "Enter" });

    const filter = await screen.findByText("Underground Piping");
    expect(filter).toBeTruthy();
    const res = await fetch(`${base}/api/drawings/${drawingId}/markups?page=${page}`);
    const rows = await res.json();
    expect(rows).toHaveLength(1);
    expect(rows[0]).toMatchObject({ kind: "polyline", inspectionType: "Underground Piping", status: "Open", createdBy: "Dom", points: [[0.26, 0.79], [0.35, 0.81]] });

    fireEvent.click(screen.getByRole("button", { name: "select" }));
    fire(layer, "pointerdown", 300, 400);
    const panel = await screen.findByLabelText("Selected markup");
    fireEvent.change(within(panel).getByLabelText("Selected status"), { target: { value: "Closed" } });
    await waitFor(async () => expect((await (await fetch(`${base}/api/drawings/${drawingId}/markups?page=${page}`)).json())[0].status).toBe("Closed"));
    fireEvent.click(within(panel).getByRole("button", { name: "Delete" }));
    await screen.findByText("No markups on this page yet.");
    expect(await (await fetch(`${base}/api/drawings/${drawingId}/markups?page=${page}`)).json()).toEqual([]);
  });
});
```

- [ ] File saved

---

## Step 20 — Frontend gate

Stop here until both commands pass. Do not mount the layer in the viewer before this.

From the repo root:

```bash
npx tsc --noEmit
npx vitest run src/lib/markup_geometry.test.ts src/components/MarkupLayer.test.tsx src/lib/procore_embed.test.ts src/components/MarkupWorkspace.e2e.test.tsx
```

Expected: no type errors, and `17 passed, 1 skipped`. The skipped test is the end-to-end file. `npm run test:unit` also runs the rest of the client tests.

- [ ] `tsc --noEmit` is clean
- [ ] The four files above are `17 passed, 1 skipped`

---

## Step 21 — Mount the layer on the existing viewer

`MarkupWorkspace` can stay as a standalone page. The app already draws the sheet in `DrawingViewer`.

The stage (`data-testid="drawing-viewer-stage"`) is `w-full` and can be wider than the image. Do not put `MarkupLayer` on that stage. Wrap the image so the layer's box is the image.

In `client/src/components/drawings/DrawingViewer.tsx`, replace the `<img data-testid="drawing-viewer-image" ... />` with a box that holds the image and the layer:

```tsx
<div className="relative inline-block">
  <img
    ref={masterImgRef}
    src={drawing.fileUrl ? apiUrl(drawing.fileUrl) : ""}
    alt={drawing.name}
    className="relative z-0 block max-h-[80vh] max-w-[1200px] select-none rounded"
    onLoad={onMasterLoad}
    onError={() => {
      setImageError(messageForDrawingImageLoadFailure(drawing.fileUrl ?? ""));
    }}
    data-testid="drawing-viewer-image"
    draggable={false}
  />
  <MarkupLayer
    markups={markups}
    tool={tool}
    visibleTypes={visibleTypes}
    selectedId={selectedId}
    onSelect={setSelectedId}
    onCreate={(kind, points, label) => create({ page, kind, points, label, inspectionType, status })}
  />
</div>
```

`markups`, `summary`, `create`, `update`, and `remove` come from:

```tsx
useDrawingMarkups(drawing.id, page, { userName })
```

Copy the toolbar and `InspectionTypeFilter` from `MarkupWorkspace` into the viewer sidebar. Leave `DrawingRegionLayer` and `useDrawingOverlays` where they are. The markup layer is a sibling of the image, inside the pan-zoom box, so zoom moves both.

The image must already be the display frame. The rendered `page-1.png` for 1722 has rotation `270` applied. Do not rotate it again in CSS.

- [ ] Layer sits on the image, not on the full-width stage
- [ ] A line drawn edge to edge lands on the page edges at two zoom levels
- [ ] Reload: the markups come back where they were drawn

---

## Step 22 — Run it inside Procore

Do this after step 21 works in a normal browser tab.

1. Register the app in the Procore developer portal as an embedded app, sandbox first. The portal screens are not covered here. The iframe-helpers package is archived, so check the current embedded-app docs before relying on it.
2. Start sign-in from the iframe with the helper. Procore's login page will not render in the frame.

```ts
import { signInThroughProcore } from "./lib/procore_embed";

await signInThroughProcore("/auth/procore");
```

3. The OAuth callback page, after the token is stored, tells the iframe that sign-in finished:

```ts
import { notifySignInDone } from "./lib/procore_embed";

await notifySignInDone();
```

4. Send `Content-Security-Policy: frame-ancestors ...` with the Procore origins that embed the app. Do not send `X-Frame-Options: DENY`. Do not use `frame-ancestors *`.
5. If the session is a cookie, set `SameSite=None; Secure`, or the browser drops it in the frame. Prefer an `Authorization` header.
6. Use `https://sandbox.procore.com` for sign-in and the API first. Switch the client id, secret, and both URLs for production.

The helper's unit tests cover the standalone redirect and a cross-origin parent. The sign-in window itself needs a registered sandbox app.

- [ ] App loads inside the sandbox
- [ ] Sign-in opens a window, closes it, and the iframe continues
- [ ] `frame-ancestors` lists only Procore origins
- [ ] Session survives a reload inside the iframe

---

## Step 23 — Follow types, then the live draw

`GET /api/drawings/{id}/markups/summary?page=N` groups live rows:

```json
[
  { "inspection_type": "Underground Piping", "status": "Closed", "count": 1 },
  { "inspection_type": "Underground Piping", "status": "Open", "count": 3 }
]
```

Until the filter is touched, every type on the page is shown. Untyped markups use the empty key, labeled "No inspection type". Colour comes from `typeColor`. Status changes and deletes reload from the server.

A markup has no inspection-run id. Adding one is a later column and query parameter, not this plan.

With the backend on the dev database, from the repo root:

```bash
E2E_URL=http://127.0.0.1:2000 E2E_DRAWING_ID=1722 E2E_PAGE=99 npx vitest run src/components/MarkupWorkspace.e2e.test.tsx
```

The dev API in this repo listens on port `2000`, not `8000`. Page `99` must have no markups. The test draws the sanitary profile stretch `[[0.26, 0.79], [0.35, 0.81]]`, checks type, status, and user, then closes and deletes it.

Then once by hand on drawing 1722:

- [ ] Draw each of the five kinds. Reload. All five are in the same places.
- [ ] Tick one type off. Only its markups disappear.
- [ ] A text note with no text creates nothing.
- [ ] A second browser shows the same markups after reload.

---

## Step 24 — Out of scope

- No import of drawing files from Procore. The sheet is one already stored here.
- No export of markups back to Procore. They live in `drawing_markups` only.
- `PATCH` accepts new points, but the layer has no drag handles. Delete and draw again.
- A second user sees new markups after a reload or the next write.
- `X-Procore-User` is a label. It does not prove who called the API.
- Stroke width is in pixels (`non-scaling-stroke`). Text notes are fixed-size HTML.
- A revision cloud is a scalloped polygon. It has no extra meaning.

---

## File map

| Path | Step |
| --- | --- |
| `backend/models/drawing_markup.py` | 2 |
| `backend/services/drawing_markups.py` | 3 |
| `backend/api/routes/drawing_markups.py` | 4 |
| `backend/database.py`, `backend/alembic/env.py`, `backend/main.py` | 5 |
| `backend/tests/test_drawing_markups.py` | 7 |
| `client/src/types/drawing_markup.ts` | 9 |
| `client/src/lib/markup_geometry.ts` | 10 |
| `client/src/lib/markup_geometry.test.ts` | 11 |
| `client/src/lib/markup_api.ts` | 12 |
| `client/src/hooks/useDrawingMarkups.ts` | 13 |
| `client/src/components/MarkupLayer.tsx` | 14 |
| `client/src/components/MarkupLayer.test.tsx` | 15 |
| `client/src/components/InspectionTypeFilter.tsx` | 16 |
| `client/src/components/MarkupWorkspace.tsx` | 17 |
| `client/src/lib/procore_embed.ts` and its test | 18 |
| `client/src/components/MarkupWorkspace.e2e.test.tsx` | 19 |
| `client/src/components/drawings/DrawingViewer.tsx` | 21 |
