"""DELETE /api/projects/{id}/drawings/{id} — hard delete, evidence links, master FK, idempotence."""

from __future__ import annotations

from typing import cast

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from models.models import (
    Drawing,
    EvidenceDrawingLink,
    EvidenceRecord,
    Project,
)
from services.storage import StorageService


def test_delete_drawing_removes_row_evidence_links_and_clears_master(
    client: TestClient, db_session: Session, project: Project
) -> None:
    storage = StorageService(db_session)
    pid = cast(int, project.id)
    master = storage.create_drawing(
        pid,
        source="upload",
        name="master.pdf",
        storage_key=f"drawings/test/{pid}/master_del.pdf",
        content_type="application/pdf",
        upload_intent="master",
    )
    sub = storage.create_drawing(
        pid,
        source="upload",
        name="sub.pdf",
        storage_key=f"drawings/test/{pid}/sub_del.pdf",
        content_type="application/pdf",
        upload_intent="sub",
    )
    mid = cast(int, master.id)
    sid = cast(int, sub.id)
    db_session.refresh(project)
    assert project.master_drawing_id == mid

    evidence = EvidenceRecord(
        project_id=pid,
        type="spec",
        title="Linked spec",
        status="new",
    )
    db_session.add(evidence)
    db_session.commit()
    db_session.refresh(evidence)
    eid = cast(int, evidence.id)
    link = EvidenceDrawingLink(
        project_id=pid,
        evidence_id=eid,
        drawing_id=mid,
    )
    db_session.add(link)
    db_session.commit()
    assert (
        db_session.query(EvidenceDrawingLink)
        .filter(EvidenceDrawingLink.drawing_id == mid)
        .count()
        == 1
    )

    response = client.delete(f"/api/projects/{pid}/drawings/{mid}")
    assert response.status_code == 204

    db_session.expire_all()
    assert db_session.query(Drawing).filter(Drawing.id == mid).first() is None
    assert (
        db_session.query(EvidenceDrawingLink)
        .filter(EvidenceDrawingLink.drawing_id == mid)
        .count()
        == 0
    )
    db_session.refresh(project)
    assert project.master_drawing_id is None
    assert storage.get_drawing(pid, sid) is not None

    again = client.delete(f"/api/projects/{pid}/drawings/{mid}")
    assert again.status_code == 404
    assert again.json() == {"detail": "Drawing not found"}
